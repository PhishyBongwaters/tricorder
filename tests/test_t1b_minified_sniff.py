"""T1 mechanism-2 red test: minified-blob content sniffing at discovery.

SPEC docs/SPEC-minified-fixture-exclusion.md mechanism 2 (trigger: Rails
MAP head still minified noise after mechanisms 1+3 — clipboard.js,
longest line 10,361 chars, mean 1,307, vs real bundles <= 1,473/48):
- single-huge-line .js/.css blobs are skipped at discovery (never enter
  tags/refs/ranks/MAP), probe parity included;
- real files with one long line but low mean (activestorage.js shape:
  longest ~1.4k, mean ~40) MUST survive — the mean guard is the point.
"""
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, '.')
from utils import discover_src_files, probe_project


def _write(root: Path, rel: str, content: str) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")


class TestT1BMinifiedSniff(unittest.TestCase):
    def _tree(self):
        ws = Path(__file__).resolve().parent.parent
        tmp = ws / ".pytest-tmp" / f"test_t1b_sniff_{id(self)}"
        import shutil
        if tmp.exists():
            shutil.rmtree(tmp)
        tmp.mkdir(parents=True, exist_ok=True)
        # Minified blob: near-zero newlines, huge mean (clipboard.js shape)
        _write(tmp, "guides/assets/clipboard.js",
               "var a=1;var b=2;var c=3;" * 2000 + "\n")
        _write(tmp, "public/legacy.css",
               ".a{color:red}.b{color:blue}" * 1500 + "\n")
        # Normal source
        _write(tmp, "src/app.js", "function hello() {\n  return 1;\n}\n")
        # Real-bundle shape: one 2.5k line, low mean -> MUST survive
        long_line = "var s = \"" + "x" * 2500 + "\";\n"
        short_lines = "".join(f"var v{i} = {i};\n" for i in range(500))
        _write(tmp, "src/bundle-real.js", long_line + short_lines)
        return tmp

    def test_blob_excluded_real_kept(self):
        from utils import _is_minified_blob  # noqa - red-first import
        tmp = self._tree()
        files = discover_src_files(str(tmp), use_gitignore=False)
        names = {os.path.relpath(f, str(tmp)).replace(os.sep, "/")
                 for f in files}
        self.assertNotIn("guides/assets/clipboard.js", names)
        self.assertNotIn("public/legacy.css", names)
        self.assertIn("src/app.js", names)
        self.assertIn("src/bundle-real.js", names,
                      "low-mean file with one long line must survive")

    def test_probe_parity(self):
        tmp = self._tree()
        probe = probe_project(str(tmp))
        # 2 kept js files: app.js, bundle-real.js
        self.assertEqual(probe["lang_counts"].get("javascript", 0), 2)


if __name__ == "__main__":
    unittest.main()
