"""Rescue pass must ignore language keywords in the query.

2026-09-25 loop autopsy (Go-G5 arm M): the agent's "func MainSSA" query
was rescued to FuncID_runtime_main (token overlap {"func","main"} is a
genuine 2/3 majority) and "func Main" to funcMap (edit distance on the
keyword-loaded core "funcmain"->"funcmap", d=2). Same junk 150 times in
a row. "func" is a language keyword, not a search signal: strip code
keywords from rescue scoring — both the overlap tokens and the
edit-distance core. Tier-1 exact/substring behavior is untouched
(rescue fires only on empty), and genuine typo rescue still works.
"""
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import Tricorder

GO_SRC = """package abi

func FuncID_runtime_main() {}

func funcMap() {}

func buildssa() {}
"""


def _project():
    tmp = Path(tempfile.mkdtemp(prefix="rescue_stop_"))
    (tmp / "m.go").write_text(GO_SRC, encoding="utf-8")
    return tmp


class TestRescueIgnoresKeywords(unittest.TestCase):
    def setUp(self):
        self.tmp = _project()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.tc = Tricorder(root=str(self.tmp), use_db=False, verbose=False,
                            output_handler_funcs={
                                'info': lambda m: None,
                                'warning': lambda m: None,
                                'error': lambda m: None})
        self.names = {t.name for t in
                      self.tc.get_tags(os.path.join(str(self.tmp), "m.go"),
                                       "m.go")}
        self.assertIn("buildssa", self.names)

    def _names(self, query):
        res, _ = self.tc.search_identifiers(query, max_results=5)
        return [r["name"] for r in res]

    def test_keyword_query_surfaces_real_evidence_only(self):
        """'func MainSSA': the rescue pass must contribute no keyword-driven
        fuzzy junk (it admitted FuncID_runtime_main pre-fix). The content
        tier may still surface genuine token evidence — including the
        answer itself via 'ssa' — which is what lets agents recover
        (r02 did exactly this). Zero-evidence symbols stay out."""
        names = self._names("func MainSSA")
        self.assertIn("buildssa", names)
        self.assertNotIn("funcMap", names)

    def test_keyword_query_does_not_rescue_edit_distance(self):
        """'func Main' must not surface funcMap: d<=2 only because the
        keyword 'func' loads the core."""
        self.assertNotIn("funcMap", self._names("func Main"))

    def test_exact_still_hits(self):
        res, rescue = self.tc.search_identifiers("buildssa", max_results=5)
        self.assertTrue(any(r["name"] == "buildssa" for r in res))
        self.assertFalse(rescue)

    def test_typo_still_rescued(self):
        """Genuine typo rescue (no keywords involved) keeps working."""
        res, rescue = self.tc.search_identifiers("buildsa", max_results=5)
        self.assertTrue(any(r["name"] == "buildssa" for r in res))
        self.assertTrue(rescue)

    def test_symbols_mirror_ignores_keywords(self):
        res, _ = self.tc.search_symbols("func MainSSA", limit=5)
        self.assertNotIn("FuncID_runtime_main",
                         [r["name"] for r in res])


if __name__ == "__main__":
    unittest.main()
