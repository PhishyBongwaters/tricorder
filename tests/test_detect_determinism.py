"""Deterministic search ordering across discovery orders.

Sort ties in the ranker used to fall through to file-discovery order
(os.walk sequence), which varies between machines and filesystems: the
same query on the same repo could return different top-N payloads on two
machines (observed as baseline drift between runs). Rank keys must break
ties on (file, line) so output depends only on repo content, never on
traversal order. See _interleave_by_file: it preserves input order, so
the sorts feeding it carry the whole determinism burden.
"""
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import Tricorder


def _repo():
    tmp = Path(tempfile.mkdtemp(prefix="determinism_"))
    # Same def name in three files: identical rank keys (kind, score,
    # name) so only the tie-break decides the order.
    for name in ("a.py", "b.py", "c.py"):
        (tmp / name).write_text("def target():\n    return 1\n",
                                encoding="utf-8", newline="\n")
    return tmp


class TestDiscoveryOrderDeterminism(unittest.TestCase):
    def setUp(self):
        self.tmp = _repo()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.tc = Tricorder(root=str(self.tmp), verbose=False)

    def _names(self, rows):
        return [(r["file"], r["line"], r["name"]) for r in rows]

    def test_identifiers_reversed_discovery(self):
        fwd = [str(self.tmp / n) for n in ("a.py", "b.py", "c.py")]
        rev = list(reversed(fwd))
        r1, _ = self.tc.search_identifiers("target", max_results=2, files=fwd)
        r2, _ = self.tc.search_identifiers("target", max_results=2, files=rev)
        self.assertEqual(self._names(r1), self._names(r2),
                         "identical query+repo must rank identically "
                         "regardless of file discovery order")

    def test_symbols_reversed_discovery(self):
        fwd = [str(self.tmp / n) for n in ("a.py", "b.py", "c.py")]
        rev = list(reversed(fwd))
        r1, _ = self.tc.search_symbols("target", limit=2, files=fwd)
        r2, _ = self.tc.search_symbols("target", limit=2, files=rev)
        self.assertEqual(self._names(r1), self._names(r2),
                         "identical query+repo must rank identically "
                         "regardless of file discovery order")

    def test_full_result_set_order_stable(self):
        # Even uncapped, the full ordering must not depend on traversal.
        fwd = [str(self.tmp / n) for n in ("a.py", "b.py", "c.py")]
        rev = list(reversed(fwd))
        r1, _ = self.tc.search_identifiers("target", max_results=200, files=fwd)
        r2, _ = self.tc.search_identifiers("target", max_results=200, files=rev)
        self.assertEqual(self._names(r1), self._names(r2))


if __name__ == "__main__":
    unittest.main()
