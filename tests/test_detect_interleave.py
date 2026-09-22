"""Regression: detect must not let one file crowd others out of the result cap.

Swift Q4 (2026-09-21 comparison): ten parseExpr* declarations in one
header filled the entire 10-result detect budget, hiding the definition
site in lib/Parse/ParseExpr.cpp. search_identifiers now interleaves hits
per file (round-robin) within each match tier before applying the cap.
"""
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import Tricorder


def _interleave():
    # Lazy import: the helper under test did not exist before the fix.
    from core import _interleave_by_file

    return _interleave_by_file


def _crowded_project():
    tmp = Path(tempfile.mkdtemp(prefix="detect_interleave_"))
    a = tmp / "a"
    b = tmp / "b"
    a.mkdir()
    b.mkdir()
    # One file with many same-name hits (the "header").
    (a / "header.py").write_text(
        "".join(f"def parse_expr_{i:02d}():\n    pass\n" for i in range(10)),
        encoding="utf-8",
    )
    # A second file with a single definition site (the "implementation").
    (b / "impl.py").write_text(
        "def parse_expr_impl():\n    pass\n", encoding="utf-8"
    )
    return tmp


class TestDetectInterleave(unittest.TestCase):
    def setUp(self):
        self.tmp = _crowded_project()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.tc = Tricorder(root=str(self.tmp), use_db=False, verbose=False)

    def test_single_file_cannot_crowd_out_other_files(self):
        results, _ = self.tc.search_identifiers("parse_expr", max_results=10)
        self.assertTrue(results)
        self.assertLessEqual(len(results), 10)
        files = {r["file"] for r in results}
        # The implementation file's lone hit must survive the cap even
        # though the header has ten same-name hits. (search_identifiers
        # reports repo-relative paths.)
        self.assertIn(str(Path("b") / "impl.py"), files)

    def test_global_top_hit_stays_first(self):
        results, _ = self.tc.search_identifiers("parse_expr", max_results=10)
        self.assertTrue(results)
        top = results[0]
        # Pin the exact top hit: interleaving must not dethrone the
        # globally best-ranked match. The old startswith("parse_expr_")
        # check also matched parse_expr_impl, so it could not catch a
        # reshuffled top result.
        self.assertEqual(top["name"], "parse_expr_00")
        self.assertEqual(top["file"], str(Path("a") / "header.py"))

    def test_interleave_unit_round_robin(self):
        _interleave_by_file = _interleave()
        items = [("a", 1), ("a", 2), ("a", 3), ("b", 1), ("c", 1)]
        out = _interleave_by_file(items, key=lambda t: t[0], limit=10)
        self.assertEqual(out, [("a", 1), ("b", 1), ("c", 1), ("a", 2), ("a", 3)])

    def test_interleave_unit_limit_and_empty(self):
        _interleave_by_file = _interleave()
        items = [("a", 1), ("b", 1), ("a", 2)]
        self.assertEqual(
            _interleave_by_file(items, key=lambda t: t[0], limit=2),
            [("a", 1), ("b", 1)],
        )
        self.assertEqual(_interleave_by_file([], key=lambda t: t[0], limit=10), [])


if __name__ == "__main__":
    unittest.main()
