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
import os
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


class TestWarmServeSkipsRepopulate(unittest.TestCase):
    """2026-09-25 finding (Go MAP timeout analysis): populate_refs()
    (12M-row cross join + full PageRank refresh) ran UNCONDITIONALLY on
    every DB-backed MAP serve — even warm-clean — so no MAP on Go could
    ever beat the 120s timeout, and read-only serves crashed outright
    (sqlite3.OperationalError: attempt to write a readonly database).
    Warm-clean serves with fresh ranks must skip repopulation; stale
    ranks backfill once with a warning; read-only views never write.
    """

    def _project(self):
        import shutil
        import tempfile
        from pathlib import Path
        tmp = Path(tempfile.mkdtemp(prefix="ranks_heal_"))
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        (tmp / "a.py").write_text("def foo():\n    return 1\n", encoding="utf-8")
        (tmp / "b.py").write_text("from a import foo\ndef bar():\n    return foo()\n",
                                  encoding="utf-8")
        db_path = str(tmp / "idx.db")
        return tmp, db_path

    def _tc(self, tmp, db_path, warnings, read_only=False):
        from core import Tricorder
        return Tricorder(root=str(tmp), use_db=True, db_path=db_path,
                         db_read_only=read_only, verbose=False,
                         output_handler_funcs={
                             'info': lambda m: None,
                             'warning': warnings.append,
                             'error': lambda m: None})

    def _files(self, tmp):
        return [os.path.join(str(tmp), f) for f in ("a.py", "b.py")]

    def _counting(self, store):
        calls = []
        orig = store.populate_refs

        def counted():
            calls.append(1)
            return orig()

        store.populate_refs = counted
        return calls

    def _stale(self, db_path):
        from database import DBStore
        db = DBStore(db_path)
        db.conn.execute("DELETE FROM file_ranks")
        db.conn.execute("DELETE FROM ranks_stamp")
        db.conn.commit()
        self.assertFalse(db.ranks_fresh())
        db.close()

    def test_warm_clean_serve_skips_populate(self):
        tmp, db_path = self._project()
        files = self._files(tmp)
        tc = self._tc(tmp, db_path, [])
        first, _ = tc.get_ranked_tags_map_uncached([], files, 2048)
        self.assertTrue(first)
        tc.close()
        # Warm, clean, ranks fresh: repopulation must not run per serve.
        tc2 = self._tc(tmp, db_path, [])
        calls = self._counting(tc2._db_store)
        second, _ = tc2.get_ranked_tags_map_uncached([], files, 2048)
        third, _ = tc2.get_ranked_tags_map_uncached([], files, 2048)
        self.assertTrue(second)
        self.assertEqual(second, third)
        self.assertEqual(calls, [],
                         "warm-clean serve repopulated refs+ranks")
        tc2.close()

    def test_stale_ranks_backfill_once_with_warning(self):
        tmp, db_path = self._project()
        files = self._files(tmp)
        tc = self._tc(tmp, db_path, [])
        tc.get_ranked_tags_map_uncached([], files, 2048)
        tc.close()
        self._stale(db_path)
        warnings = []
        tc2 = self._tc(tmp, db_path, warnings)
        calls = self._counting(tc2._db_store)
        tree, _ = tc2.get_ranked_tags_map_uncached([], files, 2048)
        self.assertTrue(tree)
        self.assertTrue(tc2._db_store.ranks_fresh(),
                        "serve did not backfill missing file_ranks")
        self.assertEqual(len(calls), 1, "stale ranks must rebuild exactly once")
        self.assertTrue(any("ranks" in w for w in warnings),
                        f"no rebuild warning emitted: {warnings}")
        # Second serve is quiet and skips: ranks now live.
        warnings.clear()
        calls.clear()
        tree2, _ = tc2.get_ranked_tags_map_uncached([], files, 2048)
        self.assertEqual(tree, tree2)
        self.assertEqual(calls, [])
        self.assertFalse(any("ranks" in w for w in warnings),
                         f"unexpected rebuild warning: {warnings}")
        tc2.close()

    def test_read_only_stale_serve_iterates_without_writes(self):
        tmp, db_path = self._project()
        files = self._files(tmp)
        tc = self._tc(tmp, db_path, [])
        tc.get_ranked_tags_map_uncached([], files, 2048)
        tc.close()
        self._stale(db_path)
        warnings = []
        tc2 = self._tc(tmp, db_path, warnings, read_only=True)
        tree, _ = tc2.get_ranked_tags_map_uncached([], files, 2048)
        self.assertTrue(tree)
        self.assertFalse(tc2._db_store.ranks_fresh(),
                         "read-only view must not write file_ranks")
        tc2.close()


if __name__ == "__main__":
    unittest.main()
