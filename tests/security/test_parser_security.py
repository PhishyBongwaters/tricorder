"""TC-010: parser fuzz fixtures + graceful-behavior test."""
import os
import sys
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.security import FIXTURES, SECURITY_DIR  # noqa: E402
from core import Tricorder  # noqa: E402


class TestParserSecurityFixtures(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        SECURITY_DIR.mkdir(parents=True, exist_ok=True)
        for name, content in FIXTURES.items():
            (SECURITY_DIR / name).write_text(content, encoding="utf-8")

    def setUp(self):
        self.repo = Tricorder(root=str(SECURITY_DIR))

    def _assert_graceful(self, fname: str):
        """A hostile file must not crash, hang, or raise — just skip/parse."""
        path = str(SECURITY_DIR / fname)
        t0 = time.monotonic()
        try:
            # get_tags_raw uses the TC-004 timeout wrapper internally.
            tags = self.repo.get_tags_raw(path, fname)
        except Exception as e:  # noqa: BLE001 - the test asserts NO exception
            self.fail(f"{fname}: parser raised {type(e).__name__}: {e}")
        dt = time.monotonic() - t0
        self.assertLess(dt, 30, f"{fname}: parse took {dt:.1f}s (possible hang)")
        self.assertIsInstance(tags, list)

    def test_deeply_nested(self):
        self._assert_graceful("deeply_nested.py")

    def test_huge_line(self):
        self._assert_graceful("huge_line.py")

    def test_malformed(self):
        self._assert_graceful("malformed.py")

    def test_unicode_idents(self):
        self._assert_graceful("unicode_idents.py")

    def test_broken_source(self):
        self._assert_graceful("broken_source.py")

    def test_giant_string(self):
        self._assert_graceful("giant_string.py")


if __name__ == "__main__":
    unittest.main()
