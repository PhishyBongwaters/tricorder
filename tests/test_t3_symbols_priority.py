"""T3 red test: symbols definition-site priority over test classes.

SPEC docs/SPEC-symbols-definition-priority.md (mechanism 3: both):
- Word-boundary rank-up: query matching a full name or a separator-
  delimited segment (Builder::HasMany) sorts above pure superstring
  matches (...HasMany...Test).
- Test-path demotion (never exclusion): test-file hits sink below
  same-rank non-test hits but stay reachable.
- CLI --symbols and MCP tricorder_symbols share core.search_symbols.
"""
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import Tricorder
from utils import symbol_boundary_rank


def _project():
    tmp = Path(tempfile.mkdtemp(prefix="t3symbols_"))
    (tmp / "pkg").mkdir()
    (tmp / "pkg" / "builder.py").write_text(
        "class HasMany:\n    def build(self):\n        return 1\n",
        encoding="utf-8",
    )
    (tmp / "tests").mkdir()
    for i, stem in enumerate(["alpha", "beta", "gamma", "delta",
                              "epsilon"]):
        cls = "Ahasmany" + stem.capitalize()
        (tmp / "tests" / f"test_{stem}.py").write_text(
            f"class {cls}:\n    def run(self):\n        return {i}\n",
            encoding="utf-8",
        )
    return tmp


class TestT3BoundaryRank(unittest.TestCase):
    def test_full_name_equality_first(self):
        self.assertEqual(symbol_boundary_rank("HasMany", "hasmany"), 0)

    def test_separator_segment_above_superstring(self):
        self.assertEqual(
            symbol_boundary_rank("Builder::HasMany", "hasmany"), 1)
        self.assertEqual(
            symbol_boundary_rank("AsyncHasManyAssociationsTest",
                                 "hasmany"), 2)

    def test_non_match_is_worst(self):
        self.assertGreaterEqual(
            symbol_boundary_rank("unrelated", "hasmany"), 2)


class TestT3SearchSymbols(unittest.TestCase):
    def setUp(self):
        self.tmp = _project()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.tc = Tricorder(root=str(self.tmp), use_db=False,
                            verbose=False)

    def _relfiles(self, results):
        return [os.path.relpath(r["file"], str(self.tmp)).replace("\\", "/")
                for r in results]

    def test_definition_site_in_top5(self):
        results, _ = self.tc.search_symbols("HasMany", limit=5)
        self.assertTrue(results)
        self.assertIn("pkg/builder.py", self._relfiles(results))

    def test_test_hits_reachable_not_excluded(self):
        results, _ = self.tc.search_symbols("HasMany", limit=50)
        files = self._relfiles(results)
        self.assertTrue(any(f.startswith("tests/") for f in files),
                        "test-file hits must stay reachable")

    def test_definition_sorts_first(self):
        results, _ = self.tc.search_symbols("HasMany", limit=5)
        first = self._relfiles(results)[0]
        self.assertEqual(first, "pkg/builder.py")


if __name__ == "__main__":
    unittest.main()
