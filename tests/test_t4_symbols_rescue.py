"""T4 red test: symbols rescue-hit ranking (definition-first).

Follow-up to the r04 leg-A call-7 notable: `symbols "Builder::HasMany"`
on an unqualified store misses the main path (no stored name contains
the full qualified string), rescue fires, and the distance sort prefers
a test class literally named `BuilderHasMany` (edit distance 2) over
the real `HasMany` definition (distance 10). Same T3 keys must govern
rescue hits: boundary rank, then test-path demotion (never exclusion),
then distance. Quality stays fuzzy (rescue contract).
"""
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import Tricorder


def _project():
    tmp = Path(tempfile.mkdtemp(prefix="t4rescue_"))
    (tmp / "pkg").mkdir()
    (tmp / "pkg" / "builder.py").write_text(
        "class HasMany:\n    def build(self):\n        return 1\n",
        encoding="utf-8",
    )
    (tmp / "tests").mkdir()
    (tmp / "tests" / "test_b.py").write_text(
        "class BuilderHasMany:\n    def run(self):\n        return 1\n",
        encoding="utf-8",
    )
    return tmp


class TestT4SymbolsRescueRanking(unittest.TestCase):
    def setUp(self):
        self.tmp = _project()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.tc = Tricorder(root=str(self.tmp), use_db=False,
                            verbose=False)

    def _relfiles(self, results):
        return [os.path.relpath(r["file"], str(self.tmp)).replace("\\", "/")
                for r in results]

    def test_rescue_promotes_definition_over_test(self):
        results, rescue = self.tc.search_symbols(
            "Builder::HasMany", limit=5)
        self.assertTrue(rescue, "main path must miss; rescue must fire")
        self.assertTrue(results)
        self.assertEqual(self._relfiles(results)[0], "pkg/builder.py")

    def test_rescue_hits_stay_fuzzy(self):
        results, rescue = self.tc.search_symbols(
            "Builder::HasMany", limit=5)
        self.assertTrue(rescue)
        self.assertTrue(results)
        for r in results:
            self.assertEqual(r.get("quality"), "fuzzy")

    def test_rescue_test_hits_reachable(self):
        results, _ = self.tc.search_symbols(
            "Builder::HasMany", limit=50)
        self.assertIn("tests/test_b.py", self._relfiles(results))


if __name__ == "__main__":
    unittest.main()
