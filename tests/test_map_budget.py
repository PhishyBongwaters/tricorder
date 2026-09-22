"""Regression: --map-tokens budget must hold, including the untagged-files section.

2026-09-21 finding: map_tokens=20 produced 37 tokens. Root cause: the
"Other files:" untagged section appended its header+tail even when the
trim loop had already emptied the kept lines, because the loop only ran
`while kept`. The section now drops instead of violating the budget
(the low-coverage warning already tells the user the map is thin).
"""
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import Tricorder
from utils import count_tokens


def _project():
    tmp = Path(tempfile.mkdtemp(prefix="map_budget_"))
    (tmp / "a.py").write_text("def a():\n    pass\n", encoding="utf-8")
    (tmp / "b.py").write_text("# no symbols here\n# just comments\n", encoding="utf-8")
    (tmp / "c.py").write_text("# also nothing\n", encoding="utf-8")
    return tmp


class TestMapTokenBudget(unittest.TestCase):
    def setUp(self):
        self.tmp = _project()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.tc = Tricorder(root=str(self.tmp), use_db=False, verbose=False)
        self.files = [os.path.join(str(self.tmp), f) for f in ("a.py", "b.py", "c.py")]

    def _tokens(self, budget):
        tree, _ = self.tc.get_ranked_tags_map_uncached([], self.files, budget)
        self.assertIsNotNone(tree)
        return count_tokens(tree)

    def test_tiny_budget_with_untagged_files_holds(self):
        # The exact 2026-09-21 repro: budget 20 produced 37 tokens.
        for budget in (20, 30, 50):
            with self.subTest(budget=budget):
                self.assertLessEqual(self._tokens(budget), budget)

    def test_generous_budget_lists_untagged_files(self):
        tree, _ = self.tc.get_ranked_tags_map_uncached([], self.files, 1000)
        self.assertIn("Other files:", tree)
        self.assertIn("b.py", tree)

    def test_budget_smaller_than_one_tag_still_returns_map(self):
        # Deliberate fallback: when not even one tag fits, emit the
        # smallest map rather than nothing (with a budget warning).
        tree, _ = self.tc.get_ranked_tags_map_uncached([], self.files, 1)
        self.assertTrue(tree)


if __name__ == "__main__":
    unittest.main()
