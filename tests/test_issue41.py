"""Issue #41 — accuracy: the map must narrow files + tokens vs blind nav.

Transportable version: instead of the Go checkout at
D:\\Projects\\Tricorder-Testing-Repos\\go (skip-if-absent), this builds a
synthetic repo in a temp dir and reuses the bench_accuracy logic, asserting
the with-Tricorder cost is strictly less than the blind cost and the task's
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


def build_synthetic_repo(root: Path, n_workers: int = 200) -> None:
    """Hub + N worker modules. The hub's methods have high fan-in, so the
    ranked map surfaces them while blind nav must read every file."""
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


class TestAccuracyNarrows(unittest.TestCase):
    def setUp(self):
        self._saved = os.environ.get("TRICORDER_CACHE_HOME")
        self._tmp = Path(tempfile.mkdtemp(prefix="issue41_cache_"))
        os.environ["TRICORDER_CACHE_HOME"] = str(self._tmp)
        utils._CACHE_ROOT = None
        self._repo = Path(tempfile.mkdtemp(prefix="issue41_repo_"))
        build_synthetic_repo(self._repo)
        self.addCleanup(self._cleanup)

    def _cleanup(self):
        import shutil
        shutil.rmtree(self._repo, ignore_errors=True)
        shutil.rmtree(self._tmp, ignore_errors=True)
        if self._saved is None:
            os.environ.pop("TRICORDER_CACHE_HOME", None)
        else:
            os.environ["TRICORDER_CACHE_HOME"] = self._saved
        utils._CACHE_ROOT = None

    def test_synthetic_map_narrows_files_and_tokens(self):
        from bench_accuracy import blind_cost, run, TRICORDER_EXE
        from bench_validity import norm
        scan_path = "."
        exclude_globs = None
        blind_files, blind_tokens = blind_cost(str(self._repo), scan_path, exclude_globs)

        td = Path(tempfile.mkdtemp(prefix="issue41_"))
        self.addCleanup(__import__("shutil").rmtree, td, True)
        map_file = td / "map.txt"
        args = ["--root", str(self._repo), "--map-tokens", "4096",
                "--exclude-untagged", "--quiet", "--output", str(map_file), scan_path]
        r = run(TRICORDER_EXE, args)
        self.assertEqual(r.returncode, 0, f"tricorder CLI failed: {r.stderr[-500:]}")
        map_text = map_file.read_text(encoding="utf-8", errors="replace")
        map_files = len({ln for ln in map_text.splitlines()
                         if ln.strip().endswith(" lines)")})
        map_tokens = utils.count_tokens(map_text)

        self.assertGreater(blind_files, 0)
        self.assertLess(map_files, blind_files,
                        "map should steer to fewer files than blind nav")
        self.assertLess(map_tokens, blind_tokens,
                        "map should cost fewer tokens than reading the repo")
        # task ground truth must be present (answerable)
        for ident in ("pick_next_task", "schedule", "update_curr"):
            self.assertIn(norm(ident), norm(map_text),
                          f"{ident} missing from map -> task not answerable")


if __name__ == "__main__":
    unittest.main()
