"""Tests for the tricorder_scan break-even advisory (advise, never refuse)."""
import asyncio
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tricorder_server import _scan_break_even_advisory


class TestScanBreakEvenAdvisory(unittest.TestCase):
    def test_none_for_nonpositive(self):
        self.assertIsNone(_scan_break_even_advisory(0))
        self.assertIsNone(_scan_break_even_advisory(-5))

    def test_small_repo_advises_skip_for_one_offs(self):
        # 76-file benchmark point: scanning buys nothing per query.
        advice = _scan_break_even_advisory(76)
        self.assertIsNotNone(advice)
        self.assertIn("76 files", advice)
        self.assertIn("skip", advice.lower())
        self.assertIn("10+", advice)
        # Advisory only: no refusal language.
        self.assertNotIn("refus", advice.lower())
        self.assertNotIn("will not", advice.lower())

    def test_large_repo_breaks_even_fast(self):
        # Django-scale point: ~60s index, pays for itself after ~1 query.
        advice = _scan_break_even_advisory(7116)
        self.assertIsNotNone(advice)
        self.assertIn("7116", advice)
        self.assertIn("~60s", advice)
        # Singular: "~1 query.", not "~1 queries".
        self.assertIn("after ~1 query.", advice)

    def test_boundary(self):
        # 200 is the documented small/large split.
        self.assertIn("Small repo", _scan_break_even_advisory(199))
        self.assertNotIn("Small repo", _scan_break_even_advisory(200))

    def test_monotone_index_cost(self):
        # Bigger repo -> weakly larger stated index cost.
        import re
        def cost(n):
            m = re.search(r"~(\d+)s", _scan_break_even_advisory(n))
            return int(m.group(1))
        self.assertLessEqual(cost(300), cost(7000))

    def test_dry_run_carries_advisory(self):
        # Integration: the dry_run planning path surfaces scan_advisory.
        from tricorder_server import tricorder_scan
        tmp = Path(tempfile.mkdtemp(prefix="scan_advisory_"))
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        (tmp / "a.py").write_text("def alpha():\n    return 1\n", encoding="utf-8")
        result = asyncio.run(tricorder_scan(
            project_root=str(tmp), dry_run=True, token_limit=2048))
        self.assertNotIn("error", result)
        self.assertIn("scan_advisory", result)
        self.assertIn("Small repo", result["scan_advisory"])


if __name__ == "__main__":
    unittest.main()
