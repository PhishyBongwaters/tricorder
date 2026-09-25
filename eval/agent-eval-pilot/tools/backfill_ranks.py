"""One-time ranks backfill for pre-precompute DBs (2026-09-25).

Opens the DB with current code (DDL creates missing file_ranks /
ranks_stamp), runs refresh_ranks() (unpersonalized PageRank over refs),
stamps current meta, checkpoints. Additive only: tags/refs/meta untouched.
Rerunnable: refresh is DELETE+INSERT under one commit.

Usage: python bench_temp/backfill_ranks.py <db-path>
"""
import sys
import time

sys.path.insert(0, '.')
from database import DBStore


def main():
    path = sys.argv[1]
    t0 = time.perf_counter()
    store = DBStore(path)
    try:
        n_tags = store.conn.execute('SELECT COUNT(*) FROM tags').fetchone()[0]
        n_refs = store.conn.execute('SELECT COUNT(*) FROM refs').fetchone()[0]
        print('db=%s tags=%d refs=%d' % (path, n_tags, n_refs), flush=True)
        store.refresh_ranks()
        n_ranks = store.conn.execute('SELECT COUNT(*) FROM file_ranks').fetchone()[0]
        print('file_ranks=%d fresh=%s elapsed=%.0fs'
              % (n_ranks, store.ranks_fresh(), time.perf_counter() - t0), flush=True)
    finally:
        store.close()


if __name__ == '__main__':
    main()
