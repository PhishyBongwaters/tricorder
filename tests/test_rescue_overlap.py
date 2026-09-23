"""Rescue overlap gate: token-overlap rescue requires a STRICT MAJORITY of
query tokens, not merely half.

A 2-token near-miss query (e.g. "compileSSA" -> {compile, ssa}) used to
rescue every symbol sharing just ONE token (every *ssa* test helper),
firing ~1.5k-token junk payloads (agent-eval v1.3 leg A-G5 cmd 5). The
overlap branch must demand overlap*2 > len(qtok): 1-token queries behave
as before, multi-token queries need a real majority.
"""
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import Tricorder


def _repo():
    tmp = Path(tempfile.mkdtemp(prefix="rescue_overlap_"))
    (tmp / "a.py").write_text(
        "def alphaOne():\n    return 1\n\n"
        "def qxTwo():\n    return 2\n\n"
        "def alphaQx():\n    return 3\n",
        encoding="utf-8", newline="\n")
    return tmp


class TestRescueOverlapMajority(unittest.TestCase):
    def setUp(self):
        self.tmp = _repo()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.tc = Tricorder(root=str(self.tmp), verbose=False)
        self.files = [str(self.tmp / "a.py")]

    def _names(self, rows):
        return [r["name"] for r in rows]

    def test_symbols_minority_overlap_excluded(self):
        # "qxAlpha" matches nothing by substring; rescue must keep only the
        # symbol sharing a MAJORITY of query tokens (alphaQx: 2/2), not the
        # single-token sharers (alphaOne, qxTwo: 1/2 each).
        rows, rescue = self.tc.search_symbols("qxAlpha", limit=10,
                                              files=self.files)
        names = self._names(rows)
        self.assertIn("alphaQx", names)
        self.assertNotIn("alphaOne", names)
        self.assertNotIn("qxTwo", names)

    def test_identifiers_minority_overlap_excluded(self):
        rows, _ = self.tc.search_identifiers("qxAlpha", max_results=10,
                                             files=self.files)
        names = self._names(rows)
        self.assertIn("alphaQx", names)
        self.assertNotIn("alphaOne", names)
        self.assertNotIn("qxTwo", names)

    def test_single_token_query_unchanged(self):
        # 1-token queries: strict majority == old behavior (overlap >= 1).
        rows, _ = self.tc.search_symbols("alphaQx", limit=10,
                                         files=self.files)
        self.assertIn("alphaQx", self._names(rows))


if __name__ == "__main__":
    unittest.main()
