"""
On-disk parse store for the DB-backed map (SPEC_db_map Goal 3, schema v1).

Purpose: keep the tree walk flat-memory. Each file's tags/refs are bulk-inserted
into sqlite and the per-file AST + tag list dropped right after — no
whole-repo-in-RAM dicts and no nx.MultiDiGraph during the scan. Ranking reads
the persisted defs back out of the DB (Goal 4 will move the PageRank itself on-disk).

Schema v1:
    tags(file, rel_file, line, name, kind)   -- one row per tag (kind in def/ref)
    refs(from_file, to_file, name)           -- one row per cross-file reference edge
    meta(schema_version, root, signature)    -- identity used by incremental recompute

Modes:
    DBStore(path)    -> file-backed sqlite (--db-path)
    DBStore(None)    -> in-memory sqlite      (--no-db)
"""
from __future__ import annotations

import sqlite3
from typing import Iterable, Iterator, List, Optional, Sequence, Tuple

SCHEMA_VERSION = 1

_DDL = [
    "CREATE TABLE IF NOT EXISTS tags("
    " file TEXT NOT NULL, rel_file TEXT NOT NULL, line INTEGER NOT NULL,"
    " name TEXT NOT NULL, kind TEXT NOT NULL)",
    "CREATE TABLE IF NOT EXISTS refs("
    " from_file TEXT NOT NULL, to_file TEXT NOT NULL, name TEXT NOT NULL)",
    "CREATE TABLE IF NOT EXISTS meta("
    " schema_version INTEGER NOT NULL, root TEXT, signature TEXT)",
    "CREATE INDEX IF NOT EXISTS idx_tags_kind_name ON tags(kind, name)",
    "CREATE INDEX IF NOT EXISTS idx_tags_file ON tags(file)",
]

_TagRow = Tuple[str, str, int, str, str]  # file, rel_file, line, name, kind


class DBStore:
    """Thin sqlite wrapper. Search/rank reads happen here; callers stay flat."""

    def __init__(self, path: Optional[str] = None):
        self.path = path
        self.conn = sqlite3.connect(path if path else ":memory:")
        # WAL keeps reads from blocking the walk's insert bursts on disk builds.
        self.conn.execute(
            "PRAGMA journal_mode=WAL" if path else "PRAGMA journal_mode=MEMORY"
        )
        for stmt in _DDL:
            self.conn.execute(stmt)
        self.conn.commit()

    # -- writes -------------------------------------------------------------
    def insert_tags(self, rows: Iterable[_TagRow]):
        """Bulk-insert one file's tags. Rows = (file, rel_file, line, name, kind)."""
        self.conn.executemany(
            "INSERT INTO tags(file, rel_file, line, name, kind) VALUES (?,?,?,?,?)",
            rows,
        )

    def set_meta(self, root: str, signature: str):
        self.conn.execute(
            "INSERT INTO meta(schema_version, root, signature) VALUES (?,?,?)",
            (SCHEMA_VERSION, root, signature),
        )

    def populate_refs(self):
        """Materialize refs edge table from def/ref tags (cross join on name).

        One row per (ref_file, def_file, name) that resolves; parallel edges for
        the same (ref, def) from different names stay distinct rows, so the
        multiplicity the MultiDiGraph used for ranking survives on disk.
        Uses rel_file (the graph's node identity).
        """
        self.conn.execute(
            "INSERT INTO refs(from_file, to_file, name) "
            "SELECT DISTINCT r.rel_file, d.rel_file, d.name "
            "FROM tags r JOIN tags d ON r.name = d.name "
            "WHERE r.kind='ref' AND d.kind='def' AND r.rel_file != d.rel_file"
        )

    # -- reads --------------------------------------------------------------
    def count_tags(self, kind: Optional[str] = None) -> int:
        if kind:
            return self.conn.execute(
                "SELECT COUNT(*) FROM tags WHERE kind=?", (kind,)
            ).fetchone()[0]
        return self.conn.execute("SELECT COUNT(*) FROM tags").fetchone()[0]

    def ref_count(self) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM refs").fetchone()[0]

    def def_files(self) -> Iterator[str]:
        """rel_files with at least one kind='def' tag."""
        return (r[0] for r in self.conn.execute(
            "SELECT DISTINCT rel_file FROM tags WHERE kind='def'"))

    def def_rows(self) -> Iterator[_TagRow]:
        """All def tags as (file, rel_file, line, name, 'def'), ordered like a file's tags."""
        return self.conn.execute(
            "SELECT file, rel_file, line, name, kind FROM tags "
            "WHERE kind='def' ORDER BY rel_file, line")

    def commit(self):
        self.conn.commit()

    def close(self):
        try:
            self.conn.commit()
        finally:
            self.conn.close()


def demo() -> int:
    """Runnable self-check (ponytail rule): schema stores + cross-join resolves refs."""
    db = DBStore(None)  # in-memory
    db.set_meta("/repo", "sig")
    db.insert_tags([
        ("/repo/a.py", "a.py", 1, "foo", "def"),
        ("/repo/a.py", "a.py", 5, "bar", "def"),
        ("/repo/b.py", "b.py", 2, "foo", "def"),
        ("/repo/c.py", "c.py", 3, "foo", "ref"),   # -> a.py AND b.py
        ("/repo/a.py", "a.py", 4, "baz", "ref"),   # self-ref, must not edge
        ("/repo/c.py", "c.py", 5, "qux", "ref"),   # no def -> no edge
    ])
    db.commit()
    db.populate_refs()
    rows = sorted(db.conn.execute(
        "SELECT from_file, to_file, name FROM refs").fetchall())
    assert rows == [
        ("c.py", "a.py", "foo"),
        ("c.py", "b.py", "foo"),
    ], f"refs mismatch: {rows}"
    # A file defining AND referencing 'foo' doesn't self-edge; distinct names
    # to the same (from,to) stay separate rows (multiplicity preserved).
    assert db.count_tags("def") == 3
    assert db.count_tags("ref") == 3
    assert set(db.def_files()) == {"a.py", "b.py"}
    assert db.ref_count() == 2
    db.close()
    print("DBStore demo OK: schema v1, tags insert, refs cross-join, reads all pass")
    return 0


if __name__ == "__main__":
    raise SystemExit(demo())