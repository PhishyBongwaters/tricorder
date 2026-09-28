"""Transcript-item 3 red test: detect test-path demotion.

From the r06A1 trail: rung-2 `detect "totp"` heads test `.ts` files
3-deep before the real defs (disableTOTP ×3, then validate_totp_code).
T3 fixed this crowding for symbols; search_identifiers still sorts
pure-substring. Same rule: demote test-path hits below same-rank
non-test hits, never exclude (test-seeking questions still reach
them). T2-safe: the smart-map skip reads quality, not order.
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
    tmp = Path(tempfile.mkdtemp(prefix="t5detect_"))
    (tmp / "src").mkdir()
    (tmp / "src" / "real.py").write_text(
        "def totp_check(secret):\n    return secret\n", encoding="utf-8")
    (tmp / "aaa").mkdir()
    (tmp / "aaa" / "test_t.py").write_text(
        "def totpwrapper(x):\n    return x\n", encoding="utf-8")
    return tmp


class TestDetectTestDemotion(unittest.TestCase):
    def setUp(self):
        self.tmp = _project()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.tc = Tricorder(root=str(self.tmp), use_db=False,
                            verbose=False)

    def _relfiles(self, results):
        out = []
        for r in results:
            f = r["file"]
            # detect returns rel_fname already; symbols returns absolute
            if os.path.isabs(f):
                f = os.path.relpath(f, str(self.tmp))
            out.append(f.replace("\\", "/"))
        return out

    def test_definition_sorts_first(self):
        # limit=None default 10; both hits fit — order is the assertion
        results, _ = self.tc.search_identifiers("totp", max_results=5)
        self.assertTrue(results)
        self.assertEqual(self._relfiles(results)[0], "src/real.py")

    def test_test_hits_reachable(self):
        results, _ = self.tc.search_identifiers("totp", max_results=50)
        self.assertIn("aaa/test_t.py", self._relfiles(results))


if __name__ == "__main__":
    unittest.main()
