"""T1 red test: minified fixture / hash-asset exclusion from discovery.

SPEC docs/SPEC-minified-fixture-exclusion.md (mechanisms 1+3):
- subtrees named fixtures/__fixtures__/testdata are skipped at discovery
- Rails/webpack fingerprinted assets <name>-<hexhash>.js/css are skipped
- normal siblings are still discovered; _MINIFIED_SUFFIXES semantics intact
"""
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, '.')
from utils import discover_src_files, probe_project


def _write(root: Path, rel: str, content: str = "var x=1;\n") -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")


class TestT1FixtureExclusion(unittest.TestCase):
    def _tree(self):
        ws = Path(__file__).resolve().parent.parent
        tmp = ws / ".pytest-tmp" / f"test_t1_fixture_{id(self)}"
        import shutil
        if tmp.exists():
            shutil.rmtree(tmp)
        tmp.mkdir(parents=True, exist_ok=True)
        # Rails-style fingerprinted fixture blob (the PageRank bomb)
        _write(tmp, "actionpack/test/fixtures/public/gzip/application-a71b3024f80aea3181c09774ca17e712.js",
               "var $=function(){}$;var A=1;var B=2;\n" * 50)
        # Normal sibling that must survive
        _write(tmp, "actionpack/lib/app.js", "function hello() {}\n")
        # Plain fixture-dir file (no hash) + testdata + __fixtures__
        _write(tmp, "pkg/fixtures/data_helper.js", "function help() {}\n")
        _write(tmp, "pkg/testdata/sample.js", "function s() {}\n")
        _write(tmp, "pkg/__fixtures__/f.js", "function f() {}\n")
        # Fingerprinted asset outside fixture dirs
        _write(tmp, "public/assets/app-9f2c4b1d3e.js", "var z=1;\n" * 10)
        _write(tmp, "public/assets/app-9f2c4b1d3e.css", ".a{color:red}\n")
        # Near-misses that must NOT be excluded
        _write(tmp, "public/assets/my-app-v2.js", "function v2() {}\n")
        _write(tmp, "src/jquery.js", "function jq() {}\n")
        return tmp

    def test_fixture_and_hash_assets_excluded(self):
        tmp = self._tree()
        files = discover_src_files(str(tmp), use_gitignore=False)
        names = {os.path.relpath(f, str(tmp)).replace(os.sep, "/") for f in files}
        for excluded in [
            "actionpack/test/fixtures/public/gzip/application-a71b3024f80aea3181c09774ca17e712.js",
            "pkg/fixtures/data_helper.js",
            "pkg/testdata/sample.js",
            "pkg/__fixtures__/f.js",
            "public/assets/app-9f2c4b1d3e.js",
            "public/assets/app-9f2c4b1d3e.css",
        ]:
            self.assertNotIn(excluded, names, f"{excluded} should be excluded")
        for kept in [
            "actionpack/lib/app.js",
            "public/assets/my-app-v2.js",
            "src/jquery.js",
        ]:
            self.assertIn(kept, names, f"{kept} should be discovered")

    def test_probe_parity(self):
        tmp = self._tree()
        probe = probe_project(str(tmp))
        # probe counts only CODE_EXTENSIONS langs; js counts.
        # 3 kept js files: app.js, my-app-v2.js, jquery.js
        self.assertEqual(probe["lang_counts"].get("javascript", 0), 3)


if __name__ == "__main__":
    unittest.main()
