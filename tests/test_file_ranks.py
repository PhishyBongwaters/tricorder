"""file_ranks: PageRank precomputed at scan time, served from the DB.

The DB backend's entire point is preload: parse once, rank once, serve
forever. Every MAP call used to run SQL power iteration fresh over refs
(~12M rows on Go) then stream all def rows — even on a warm DB. These
tests pin the preload contract:

- refresh_ranks() stores one rank per def file, stamped with the current
  meta (signature + extractor_version).
- ranks_fresh() is True iff the stamp matches current meta.
- get_ranks() returns the stored mapping for the serve path.
- populate_refs() refreshes ranks (single production hook: full and
  incremental scans both end there), so ranks can never silently stale.
"""
import sys
import unittest
sys.path.insert(0, '.')
from database import DBStore


def _tags():
    # a.py defines foo+bar; b.py refs foo (edge b->a); c.py standalone.
    return [
        ("a.py", "a.py", 1, "foo", "def"),
        ("a.py", "a.py", 5, "bar", "def"),
        ("b.py", "b.py", 2, "foo", "ref"),
        ("c.py", "c.py", 1, "qux", "def"),
    ]


def _db():
    db = DBStore(None)
    db.insert_tags(_tags())
    db.set_meta("/root", "sig1")
    db.populate_refs()
    return db


class TestFileRanks(unittest.TestCase):
    def test_refresh_stores_all_def_files(self):
        db = _db()
        db.refresh_ranks()
        rows = dict(db.conn.execute(
            "SELECT rel_file, rank FROM file_ranks").fetchall())
        # Every mapped file holds rank (ref-only b.py votes but has no defs;
        # the serve path looks up def files only).
        self.assertEqual(set(rows), {"a.py", "b.py", "c.py"})
        for r in rows.values():
            self.assertGreater(r, 0.0)

    def test_ranks_sum_to_one(self):
        db = _db()
        db.refresh_ranks()
        total = db.conn.execute(
            "SELECT SUM(rank) FROM file_ranks").fetchone()[0]
        self.assertAlmostEqual(total, 1.0, places=3)

    def test_referenced_file_outranks_standalone(self):
        # b.py -> a.py edge: a.py must outrank unreferenced c.py.
        db = _db()
        db.refresh_ranks()
        ranks = dict(db.get_ranks())
        self.assertGreater(ranks["a.py"], ranks["c.py"])

    def test_stamp_fresh_then_stale(self):
        db = _db()
        db.refresh_ranks()
        self.assertTrue(db.ranks_fresh())
        db.set_meta("/root", "sig2")  # repo changed: stamp must mismatch
        self.assertFalse(db.ranks_fresh())

    def test_populate_refs_refreshes_ranks(self):
        db = _db()
        # ranks written by the scan-end hook itself, no separate call.
        self.assertTrue(db.ranks_fresh())
        self.assertEqual({r for r, _ in db.get_ranks()},
                         {"a.py", "b.py", "c.py"})

    def test_serve_equivalence(self):
        # Stored ranks must equal iterated ranks for the same graph (all
        # mapped files as nodes, serve-path semantics).
        db = _db()
        db.refresh_ranks()
        live = db.pagerank(iter(["a.py", "b.py", "c.py"]))
        stored = dict(db.get_ranks())
        self.assertEqual(set(live), set(stored))
        for f in live:
            self.assertAlmostEqual(live[f], stored[f], places=6)


if __name__ == "__main__":
    unittest.main()
