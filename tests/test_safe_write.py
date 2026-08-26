"""Regression test for safe_write() containment guard (TC-006/TC-008).

The never-write-to-scanned-repo invariant must hold structurally: any in-process
write that would land outside the cache root raises instead of silently escaping.
"""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, ".")
from utils import get_cache_root, safe_write, _get_budget_cache_path


class TestSafeWrite(unittest.TestCase):
    def test_write_inside_cache_root_ok(self):
        target = get_cache_root() / "test_safe_write" / "ok.json"
        out = safe_write(target, '{"ok": true}')
        self.assertTrue(out.exists())
        self.assertEqual(out.read_text(encoding="utf-8"), '{"ok": true}')
        out.unlink()

    def test_escape_outside_root_raises(self):
        with tempfile.TemporaryDirectory() as d:
            escape = Path(d) / "escape.json"
            with self.assertRaises(ValueError):
                safe_write(escape, "x")

    def test_allow_escape_writes_anywhere(self):
        with tempfile.TemporaryDirectory() as d:
            out = safe_write(Path(d) / "free.json", "x", allow_escape=True)
            self.assertTrue(out.exists())

    def test_real_sites_inside_root(self):
        # Production write targets must all resolve under the cache root so the
        # default (allow_escape=False) guard never trips on legitimate writes.
        root = get_cache_root()
        budget_path = _get_budget_cache_path(str(root))
        self.assertIsNotNone(budget_path)
        self.assertIn(root, Path(budget_path).resolve().parents)
        server_out = root / "output" / "scan.json"
        self.assertIn(root, server_out.resolve().parents)
        self.assertIn(root, (root / ".tricorder" / "indexes" / "x" / "meta.json").parents)
