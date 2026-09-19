"""Tests for delta maps: Tricorder.diff_against_index + tricorder_diff MCP tool."""
import asyncio
import os
import shutil
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import Tricorder
from database import DBStore


def _write(p: Path, text: str):
    p.write_text(text, encoding="utf-8")


class TestDiffAgainstIndex(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="diff_"))
        # Mirror production layout: the index DB lives under .tricorder/,
        # which discover_src_files skips (dot-dir rule).
        (self.tmp / ".tricorder").mkdir()
        self.db_path = str(self.tmp / ".tricorder" / "idx.db")
        _write(self.tmp / "a.py", "def alpha():\n    return 1\n")
        _write(self.tmp / "b.py", "def beta():\n    return 2\n")
        # Force distinct mtimes (filesystem granularity).
        time.sleep(0.02)
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def _index(self):
        """Record current file_state as if a scan just completed."""
        db = DBStore(self.db_path)
        for f in ("a.py", "b.py"):
            st = os.stat(self.tmp / f)
            db.set_file_state(f, st.st_size, int(st.st_mtime))
        db.conn.commit()
        db.conn.close()

    def _tricorder(self):
        return Tricorder(root=str(self.tmp), db_path=self.db_path, verbose=False)

    def test_no_changes(self):
        self._index()
        d = self._tricorder().diff_against_index()
        self.assertTrue(d["indexed"])
        self.assertEqual(d["added"], [])
        self.assertEqual(d["modified"], [])
        self.assertEqual(d["deleted"], [])

    def test_added_modified_deleted(self):
        self._index()
        time.sleep(0.02)
        _write(self.tmp / "a.py", "def alpha():\n    return 1\n\ndef gamma():\n    return 3\n")
        _write(self.tmp / "c.py", "x = 1\n")
        (self.tmp / "b.py").unlink()
        # Bump mtime explicitly (some filesystems have coarse granularity).
        now = time.time() + 5
        os.utime(self.tmp / "a.py", (now, now))

        d = self._tricorder().diff_against_index()
        self.assertEqual(d["added"], ["c.py"])
        self.assertEqual(d["modified"], ["a.py"])
        self.assertEqual(d["deleted"], ["b.py"])
        # Delta map carries tags for changed files only.
        self.assertIn("a.py", d["tags"])
        self.assertIn("c.py", d["tags"])
        self.assertNotIn("b.py", d["tags"])
        names = {t["name"] for t in d["tags"]["a.py"]}
        self.assertIn("alpha", names)
        self.assertIn("gamma", names)

    def test_never_scanned(self):
        d = self._tricorder().diff_against_index()
        self.assertFalse(d["indexed"])
        self.assertEqual(sorted(d["added"]), ["a.py", "b.py"])
        self.assertEqual(d["modified"], [])
        self.assertEqual(d["deleted"], [])

    def test_no_db(self):
        t = Tricorder(root=str(self.tmp), use_db=False, verbose=False)
        d = t.diff_against_index()
        self.assertFalse(d["indexed"])
        self.assertEqual(sorted(d["added"]), ["a.py", "b.py"])

    def test_mcp_tool(self):
        from tricorder_server import tricorder_diff
        self._index()
        result = asyncio.run(tricorder_diff(project_root=str(self.tmp)))
        # Server resolves the canonical DB; with a custom db_path there is
        # none, so it reports unindexed — but must not error.
        self.assertNotIn("error", result)
        self.assertIn("added", result)
        self.assertIn("modified", result)
        self.assertIn("deleted", result)


if __name__ == "__main__":
    unittest.main()
