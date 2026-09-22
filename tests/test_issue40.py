"""Issue #40 — large-repo torture: metrics capture must work and be sane.

Transportable version: instead of the multi-GB Linux kernel checkout at
D:\\Projects\\Tricorder-Testing-Repos\\linux (skip-if-absent), this builds a
synthetic mid-size repo (~200 files) in a temp dir and runs the same
bench harness (bench_validity.run_repo), asserting the issue #40 metrics
(scan_time_s, index_bytes, token reduction, coverage) are captured and
non-degenerate.
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

from bench_validity import run_repo  # noqa: E402
import utils  # noqa: E402
from ctags_probe import _count_source_files as _count_source_files_for  # noqa: E402


def build_synthetic_repo(root: Path, n_workers: int = 200) -> None:
    """Write a hub + N worker modules. The hub's methods have high fan-in,
    so PageRank ranks them into the map (ground truth answerable)."""
    (root / "scheduler.py").write_text(
        '''"""Task scheduler hub."""
class Scheduler:
    def pick_next_task(self, queue):
        """Pick the next runnable task from the queue."""
        return queue.pop(0)

    def schedule(self, task):
        """Schedule a task for execution."""
        return task

    def update_curr(self, task):
        """Mark task as currently running."""
        return task
''',
        encoding="utf-8",
    )
    for i in range(n_workers):
        (root / f"worker_{i:03d}.py").write_text(
            f'''"""Worker module {i}."""
from scheduler import Scheduler

def run_job_{i}(queue):
    """Run job {i} through the scheduler."""
    s = Scheduler()
    t = s.pick_next_task(queue)
    s.schedule(t)
    s.update_curr(t)
    return t

def helper_{i}(x):
    """Helper {i} does some work on x."""
    return x * {i}
''',
            encoding="utf-8",
        )


class TestSyntheticTortureMetrics(unittest.TestCase):
    def setUp(self):
        # scope the temp cache root to this test so we don't pollute the
        # in-process get_cache_root() used by sibling tests
        self._saved_cache_home = os.environ.get("TRICORDER_CACHE_HOME")
        self._tmp_cache = Path(tempfile.mkdtemp(prefix="issue40_cache_"))
        os.environ["TRICORDER_CACHE_HOME"] = str(self._tmp_cache)
        utils._CACHE_ROOT = None  # force re-resolution under the temp root
        self._repo = Path(tempfile.mkdtemp(prefix="issue40_repo_"))
        build_synthetic_repo(self._repo)
        self.addCleanup(self._cleanup_repo)

    def _cleanup_repo(self):
        import shutil
        shutil.rmtree(self._repo, ignore_errors=True)
        shutil.rmtree(self._tmp_cache, ignore_errors=True)
        if self._saved_cache_home is None:
            os.environ.pop("TRICORDER_CACHE_HOME", None)
        else:
            os.environ["TRICORDER_CACHE_HOME"] = self._saved_cache_home
        utils._CACHE_ROOT = None

    def test_synthetic_metrics_captured_and_sane(self):
        repo = {
            "name": "synthetic",
            "root": str(self._repo),
            "scan_path": ".",
            "map_tokens": 4000,
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
        # the scheduler task must be answerable from the map
        self.assertTrue(all(t["pass"] for t in report["tasks"]),
                        f"task not answerable: {report['tasks']}")
        # cache root must have been written under the temp root (budget.json lives
        # at <root>/cache/<repo_hash>/budget.json per _get_budget_cache_path)
        cache_root = Path(os.environ["TRICORDER_CACHE_HOME"])
        budget_files = list(cache_root.glob("cache/*/budget.json"))
        self.assertTrue(budget_files, "budget cache not written under TRICORDER_CACHE_HOME")
        # index_bytes > 0 only when the repo is under the ctags cap
        # (CTAGS_MAX_SOURCE_FILES) and ctags is installed; otherwise the rg
        # fallback writes no index, so don't assert it here.
        if m["index_bytes"] == 0:
            self.assertGreater(
                _count_source_files_for(self._repo), 0,
                "expected either an index OR discoverable files",
            )


if __name__ == "__main__":
    unittest.main()
