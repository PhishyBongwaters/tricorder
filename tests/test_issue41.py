"""Issue #41 — accuracy: the map must narrow files + tokens vs blind nav.

Reuses bench_accuracy logic on a small present repo (go) and asserts the
with-Tricorder cost is strictly less than the blind cost, and the task's
ground truth is answerable from the map. This is the reproducible proxy for
the 'does the map actually help an agent' killer metric (no live LLM needed).
"""
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "bench"))

import utils  # noqa: E402

GO_ROOT = Path(r"D:\Projects\Tricorder-Testing-Repos\go")


@unittest.skipUnless(GO_ROOT.is_dir(), "go checkout not present")
class TestAccuracyNarrows(unittest.TestCase):
    def setUp(self):
        self._saved = os.environ.get("TRICORDER_CACHE_HOME")
        self._tmp = Path(tempfile.mkdtemp(prefix="issue41_cache_"))
        os.environ["TRICORDER_CACHE_HOME"] = str(self._tmp)
        utils._CACHE_ROOT = None

    def tearDown(self):
        import shutil
        shutil.rmtree(self._tmp, ignore_errors=True)
        if self._saved is None:
            os.environ.pop("TRICORDER_CACHE_HOME", None)
        else:
            os.environ["TRICORDER_CACHE_HOME"] = self._saved
        utils._CACHE_ROOT = None

    def test_go_map_narrows_files_and_tokens(self):
        from bench_accuracy import blind_cost, run, TRICORDER_EXE
        from bench_validity import norm
        scan_path = "src/cmp"
        exclude_globs = None
        blind_files, blind_tokens = blind_cost(str(GO_ROOT), scan_path, exclude_globs)

        td = Path(tempfile.mkdtemp(prefix="issue41_"))
        map_file = td / "map.txt"
        args = ["--root", str(GO_ROOT), "--map-tokens", "4096",
                "--exclude-untagged", "--quiet", "--output", str(map_file), scan_path]
        run(TRICORDER_EXE, args)
        map_text = map_file.read_text(encoding="utf-8", errors="replace")
        map_files = len({ln for ln in map_text.splitlines()
                         if ln.strip().endswith(" lines)")})
        map_tokens = utils.count_tokens(map_text)

        self.assertGreater(blind_files, 0)
        self.assertLess(map_files, blind_files,
                        "map should steer to fewer files than blind nav")
        self.assertLess(map_tokens, blind_tokens,
                        "map should cost fewer tokens than reading the repo")
        # go task ground truth must be present (answerable)
        for ident in ("Less", "Compare", "Or"):
            self.assertIn(norm(ident), norm(map_text),
                          f"{ident} missing from map -> task not answerable")
        import shutil as _sh
        _sh.rmtree(td, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
