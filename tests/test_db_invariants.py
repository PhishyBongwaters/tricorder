"""DB invariant tests: stacking, truncation, and ref-bloat guards.

Uses DBStore(None) (in-memory) only — never touches disk.
Cf. dbdc07e (stacking), f57ef19 (--max-files truncation probe).
"""
import sys
import unittest
sys.path.insert(0, '.')
from database import DBStore


def _sample_tags():
    # (file, rel_file, line, name, kind)
    return [
        ("a.py", "a.py", 1, "foo", "def"),
        ("a.py", "a.py", 5, "bar", "def"),
        ("b.py", "b.py", 2, "foo", "ref"),
        ("b.py", "b.py", 3, "baz", "ref"),  # unresolvable ref
    ]


class TestDbInvariants(unittest.TestCase):
    def test_meta_stays_one_row(self):
        db = DBStore(None)
        db.set_meta("/root", "sig1")
        db.set_meta("/root", "sig2")
        db.set_meta("/other", "sig3")
        n = db.conn.execute("SELECT COUNT(*) FROM meta").fetchone()[0]
        self.assertEqual(n, 1)

    def test_reset_clears_all_tables(self):
        db = DBStore(None)
        db.insert_tags(_sample_tags())
        db.set_file_state("a.py", 100, 123)
        db.set_meta("/root", "sig")
        db.populate_refs()
        db.reset()
        for tbl in ("tags", "refs", "meta", "file_state"):
            n = db.conn.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()[0]
            self.assertEqual(n, 0, tbl)

    def test_file_state_matches_tags(self):
        db = DBStore(None)
        db.insert_tags(_sample_tags())
        db.set_file_state("a.py", 100, 123)
        db.set_file_state("b.py", 200, 456)
        tag_files = {r[0] for r in db.conn.execute("SELECT DISTINCT rel_file FROM tags")}
        state_files = set(db.get_file_state())
        self.assertEqual(tag_files, state_files)

    def test_populate_refs_idempotent(self):
        # Second run must not grow refs (incremental path calls it repeatedly).
        db = DBStore(None)
        db.insert_tags(_sample_tags())
        db.populate_refs()
        first = db.conn.execute("SELECT COUNT(*) FROM refs").fetchone()[0]
        self.assertGreater(first, 0)  # b.py foo-ref -> a.py foo-def
        db.populate_refs()
        second = db.conn.execute("SELECT COUNT(*) FROM refs").fetchone()[0]
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
