"""Issue #39 — regression validation: targeted tests per resolved fix.

Three concrete cases called out in the issue:
1. full_repo_estimate / savings_pct exact relationship (not just >90).
2. Tier-history store stays bounded under a 100k-scan stress loop (no leak).
3. ctags index invalidates + regenerates on repo change (end-to-end path that
   the phase-1 suite did NOT exercise — it only tested the staleness logic).
"""
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

sys_path_inserted = False
import sys as _sys
if str(Path(__file__).parent.parent) not in _sys.path:
    _sys.path.insert(0, str(Path(__file__).parent.parent))
    sys_path_inserted = True

from utils import repo_budget, calculate_full_repo_budget  # noqa: E402
from ctags_probe import ensure_ctags_index, _read_tags_meta, _get_meta_cache_path  # noqa: E402
from tricorder_server import (_tier_history_store, _tier_history_set, _MAX_TIER_HISTORY)  # noqa: E402


class TestFullRepoEstimateExact(unittest.TestCase):
    def setUp(self):
        self.project_root = str(Path(__file__).parent.parent.resolve())

    def test_savings_pct_matches_formula(self):
        """savings_pct must equal round((1 - map/full)*100, 1) exactly."""
        full = repo_budget(self.project_root, 0)["full_repo_estimate"]
        self.assertGreater(full, 0)
        for map_tokens in (1, 1000, full // 2, full - 1):
            r = repo_budget(self.project_root, map_tokens)
            expected = round(max(0.0, 1 - map_tokens / full) * 100, 1)
            self.assertEqual(r["savings_pct"], expected,
                             f"savings_pct mismatch at map_tokens={map_tokens}")

    def test_full_repo_estimate_independent_of_map_tokens(self):
        """full_repo_estimate is the repo size, not the map size."""
        a = calculate_full_repo_budget(self.project_root, 1, force_refresh=True)
        b = calculate_full_repo_budget(self.project_root, 999999)
        self.assertEqual(a["full_repo_estimate"], b["full_repo_estimate"])

    def test_map_equals_full_yields_zero_savings(self):
        full = repo_budget(self.project_root, 0)["full_repo_estimate"]
        r = repo_budget(self.project_root, full)
        self.assertEqual(r["savings_pct"], 0.0)


class TestTierHistoryStress(unittest.TestCase):
    def test_bounded_under_100k_scans(self):
        """100k project scans must not grow the tier-history store."""
        _tier_history_store.clear()
        for i in range(100_000):
            _tier_history_set(
                f"proj_{i}",
                {"last_tier": i % 2, "last_format": "text", "map_file": f"m{i}.txt"},
            )
        self.assertEqual(len(_tier_history_store), _MAX_TIER_HISTORY)
        # spot-check a recent entry survived (LRU kept it)
        self.assertIsNotNone(_tier_history_store.get(f"proj_{100_000 - 1}"))


class TestCtagsRegenerateOnChange(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="issue39_ctags_"))
        subprocess.run(["git", "init", "-q", str(self.tmp)], check=True)
        subprocess.run(["git", "-C", str(self.tmp), "config", "user.email", "t@t"], check=True)
        subprocess.run(["git", "-C", str(self.tmp), "config", "user.name", "t"], check=True)
        (self.tmp / "a.py").write_text("def alpha():\n    return 1\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(self.tmp), "add", "-A"], check=True)
        subprocess.run(["git", "-C", str(self.tmp), "commit", "-q", "-m", "init"], check=True)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _commit_change(self):
        # change content AND commit so git_commit advances
        (self.tmp / "a.py").write_text(
            "def alpha():\n    return 2\n\ndef beta():\n    return 3\n",
            encoding="utf-8",
        )
        subprocess.run(["git", "-C", str(self.tmp), "add", "-A"], check=True)
        subprocess.run(["git", "-C", str(self.tmp), "commit", "-q", "-m", "change"], check=True)

    def test_regenerates_after_repo_change(self):
        first = ensure_ctags_index(str(self.tmp))
        self.assertIsNotNone(first, "ctags index should build")
        meta_path = _get_meta_cache_path(str(self.tmp))
        first_commit = _read_tags_meta(meta_path)["git_commit"]

        self._commit_change()
        second = ensure_ctags_index(str(self.tmp))
        self.assertIsNotNone(second, "index should regenerate after change")
        second_commit = _read_tags_meta(meta_path)["git_commit"]
        self.assertNotEqual(first_commit, second_commit,
                            "meta must record the new commit after regeneration")
        self.assertEqual(second_commit,
                         subprocess.run(["git", "-C", str(self.tmp), "rev-parse", "HEAD"],
                                        capture_output=True, text=True).stdout.strip())


if __name__ == "__main__":
    unittest.main()
