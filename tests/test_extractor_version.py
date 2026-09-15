"""Extractor version stamping: full scans certify, incremental preserves."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from database import DBStore, EXTRACTOR_VERSION


class TestExtractorVersion(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        self.db = DBStore(self.tmp.name)

    def tearDown(self):
        self.db.conn.close()
        Path(self.tmp.name).unlink(missing_ok=True)

    def test_full_stamp(self):
        self.db.set_meta("/r", "sig", EXTRACTOR_VERSION)
        self.assertEqual(self.db.get_meta()[3], EXTRACTOR_VERSION)

    def test_incremental_preserves(self):
        self.db.set_meta("/r", "sig", EXTRACTOR_VERSION)
        self.db.set_meta("/r", "sig2")  # incremental: no version arg
        self.assertEqual(self.db.get_meta()[3], EXTRACTOR_VERSION)

    def test_fresh_unstamped_reads_zero(self):
        self.db.set_meta("/r", "sig")
        self.assertEqual(self.db.get_meta()[3], 0)

    def test_migration_adds_column(self):
        import sqlite3
        p = self.tmp.name + ".old"
        con = sqlite3.connect(p)
        con.execute("CREATE TABLE meta(schema_version INTEGER, root TEXT, signature TEXT)")
        con.execute("INSERT INTO meta VALUES (1,'/r','s')")
        con.commit()
        con.close()
        db2 = DBStore(p)
        try:
            self.assertEqual(db2.get_meta()[3], 0)
            db2.set_meta("/r", "s", EXTRACTOR_VERSION)
            self.assertEqual(db2.get_meta()[3], EXTRACTOR_VERSION)
        finally:
            db2.conn.close()
            Path(p).unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
