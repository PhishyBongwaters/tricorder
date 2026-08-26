"""Issue #43 — cache integrity across branch switch / rebase / config change.

The ctags index cache (ctags_probe) is keyed by git_commit + file_count + age
in tags.meta.json. This test asserts that staleness detection actually fires on
each of those events so a switched branch / rebased repo / changed file set
never serves a stale index. No ctags CLI needed — we exercise _is_meta_stale
directly against a real temp git repo.
"""
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import ctags_probe  # noqa: E402
import utils  # noqa: E402


def _git(repo, *args):
    subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True,
                   check=True, timeout=30)


def _make_repo():
    repo = Path(tempfile.mkdtemp())
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "t@t")
    _git(repo, "config", "user.name", "t")
    (repo / "a.py").write_text("def f():\n    return 1\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "init")
    return repo


class TestCacheIntegrity(unittest.TestCase):
    def setUp(self):
        self._saved = os.environ.get("TRICORDER_CACHE_HOME")
        self._tmp = Path(tempfile.mkdtemp(prefix="issue43_cache_"))
        os.environ["TRICORDER_CACHE_HOME"] = str(self._tmp)
        utils._CACHE_ROOT = None
        self.repo = _make_repo()
        self.excludes = ["*.min.js"]

    def tearDown(self):
        import shutil
        shutil.rmtree(self._tmp, ignore_errors=True)
        shutil.rmtree(self.repo, ignore_errors=True)
        if self._saved is None:
            os.environ.pop("TRICORDER_CACHE_HOME", None)
        else:
            os.environ["TRICORDER_CACHE_HOME"] = self._saved
        utils._CACHE_ROOT = None

    def _fresh_meta(self):
        return {
            "git_commit": ctags_probe._get_git_commit(str(self.repo)),
            "file_count": ctags_probe._count_source_files(str(self.repo),
                                                          exclude_globs=self.excludes),
            "generated": time.time(),
        }

    def test_fresh_cache_not_stale(self):
        self.assertFalse(
            ctags_probe._is_meta_stale(self._fresh_meta(), str(self.repo),
                                       self.excludes, 7),
            "a just-written cache keyed to HEAD+file_count must be fresh",
        )

    def test_branch_switch_invalidates(self):
        # new commit on another branch changes HEAD -> git_commit mismatch
        _git(self.repo, "checkout", "-qb", "feature")
        (self.repo / "b.py").write_text("def g():\n    return 2\n")
        _git(self.repo, "add", "-A")
        _git(self.repo, "commit", "-qm", "add b")
        old = self._fresh_meta()
        # meta captured the NEW commit, so simulate an OLD meta by rewriting
        # git_commit to the previous HEAD
        prev = subprocess.run(["git", "rev-parse", "HEAD~1"], cwd=self.repo,
                               capture_output=True, text=True, check=True).stdout.strip()
        old["git_commit"] = prev
        self.assertTrue(
            ctags_probe._is_meta_stale(old, str(self.repo), self.excludes, 7),
            "branch switch / rebase (HEAD commit change) must invalidate cache",
        )

    def test_file_count_change_invalidates(self):
        meta = self._fresh_meta()
        # simulate a config change that adds a source file
        (self.repo / "c.py").write_text("def h():\n    return 3\n")
        self.assertTrue(
            ctags_probe._is_meta_stale(meta, str(self.repo), self.excludes, 7),
            "file set change (file_count) must invalidate cache",
        )

    def test_age_invalidates(self):
        meta = self._fresh_meta()
        meta["generated"] = time.time() - 8 * 86400  # older than max_age_days=7
        self.assertTrue(
            ctags_probe._is_meta_stale(meta, str(self.repo), self.excludes, 7),
            "aged cache (8d > 7d) must invalidate",
        )


if __name__ == "__main__":
    unittest.main()
