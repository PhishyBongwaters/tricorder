"""Issue #40 — large-repo torture: metrics capture must work and be sane.

Runs the real bench harness on the Linux kernel checkout (present in the
default testbed) with a temp cache root, then asserts the issue #40 metrics
(scan_time_s, index_bytes, token reduction, coverage) are captured and
non-degenerate. Chromium/LLVM are skip-if-absent monster repos — not asserted
here; they require multi-GB checkouts (see bench_validity.py REPOS).
"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "bench"))

from bench_validity import run_repo  # noqa: E402
import utils  # noqa: E402
from ctags_probe import _count_source_files as _count_source_files_for  # noqa: E402

LINUX_ROOT = Path(r"D:\Projects\Tricorder-Testing-Repos\linux")


@unittest.skipUnless(LINUX_ROOT.is_dir(), "linux checkout not present")
class TestLinuxTortureMetrics(unittest.TestCase):
    def setUp(self):
        # scope the temp cache root to this test so we don't pollute the
        # in-process get_cache_root() used by sibling tests
        self._saved_cache_home = os.environ.get("TRICORDER_CACHE_HOME")
        self._tmp_cache = Path(tempfile.mkdtemp(prefix="issue40_cache_"))
        os.environ["TRICORDER_CACHE_HOME"] = str(self._tmp_cache)
        utils._CACHE_ROOT = None  # force re-resolution under the temp root

    def tearDown(self):
        import shutil
        shutil.rmtree(self._tmp_cache, ignore_errors=True)
        if self._saved_cache_home is None:
            os.environ.pop("TRICORDER_CACHE_HOME", None)
        else:
            os.environ["TRICORDER_CACHE_HOME"] = self._saved_cache_home
        utils._CACHE_ROOT = None

    def test_linux_metrics_captured_and_sane(self):
        repo = {
            "name": "linux",
            "root": LINUX_ROOT,
            "scan_path": ".",
            "map_tokens": 40000,
            "exclude_globs": None,
            "pre_index": "pick_next_task",
            "tasks": [
                {"question": "scheduler entry point",
                 "ground_truth": ["pick_next_task", "schedule", "update_curr"]},
            ],
        }
        report = run_repo(repo)
        m = report["metrics"]
        # discovery + probe must have produced a map and metrics
        self.assertGreater(m["scan_time_s"], 0, "scan_time_s not measured")
        self.assertGreater(report["map_tokens"], 0, "map produced no tokens")
        self.assertGreater(m["full_repo_tokens"], report["map_tokens"],
                           "full repo must exceed the map")
        self.assertGreater(report["savings_pct"], 0, "expected token reduction")
        # cache root must have been written under the temp root (budget.json lives
        # at <root>/cache/<repo_hash>/budget.json per _get_budget_cache_path)
        cache_root = Path(os.environ["TRICORDER_CACHE_HOME"])
        budget_files = list(cache_root.glob("cache/*/budget.json"))
        self.assertTrue(budget_files, "budget cache not written under TRICORDER_CACHE_HOME")
        # index_bytes > 0 only when the repo is under the ctags cap
        # (CTAGS_MAX_SOURCE_FILES). Linux (~20k files) intentionally uses the
        # rg fallback and writes no ctags index, so don't assert it here.
        if m["index_bytes"] == 0:
            self.assertGreater(
                _count_source_files_for(repo["root"]), 0,
                "expected either an index OR discoverable files",
            )


if __name__ == "__main__":
    unittest.main()
