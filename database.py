"""
On-disk parse store for the DB-backed map (SPEC_db_map Goal 3, schema v1).

Purpose: keep the tree walk flat-memory. Each file's tags/refs are bulk-inserted
into sqlite and the per-file AST + tag list dropped right after — no
whole-repo-in-RAM dicts and no nx.MultiDiGraph during the scan. Ranking reads
the persisted defs back out of the DB (Goal 4 will move the PageRank itself on-disk).

Schema v1:
    tags(file, rel_file, line, name, kind)   -- one row per tag (kind in def/ref)
    refs(from_file, to_file, name)           -- one row per cross-file reference edge
    meta(schema_version, root, signature, extractor_version) -- identity + extractor stamp
    file_state(rel_file, size, mtime)        -- per-file stat fingerprint (size, mtime_ns)
    stop_names(name)                         -- def-names skipped by populate_refs (>50 files)
    file_flags(rel_file, reason)             -- why a scanned file owns zero tags

Modes:
    DBStore(path)    -> file-backed sqlite (--db-path)
    DBStore(None)    -> in-memory sqlite      (--no-db)
    DBStore(path, read_only=True) -> file-backed sqlite, frozen
        (mode=ro&immutable=1, no DDL/migration/commit)
"""
from __future__ import annotations

import os
import sqlite3
import threading
from typing import Dict, Iterable, Iterator, List, Optional, Sequence, Tuple

from utils import read_only_connect

SCHEMA_VERSION = 1

# Version of the tag-extraction logic (tree-sitter queries/captures in
# queries/, parser.py, import_parser.py). Stamped into meta on full scans;
# the audit flags DBs stamped older. Bump on ANY capture change.
# Separate lineage from cache.CACHE_VERSION (query-time bundles) — a
# query-time fix must NOT force tag reparse, and vice versa.
EXTRACTOR_VERSION = 2

_DDL = [
    "CREATE TABLE IF NOT EXISTS tags("
    " file TEXT NOT NULL, rel_file TEXT NOT NULL, line INTEGER NOT NULL,"
    " name TEXT NOT NULL, kind TEXT NOT NULL)",
    "CREATE TABLE IF NOT EXISTS refs("
    " from_file TEXT NOT NULL, to_file TEXT NOT NULL, name TEXT NOT NULL)",
    "CREATE TABLE IF NOT EXISTS meta("
    " schema_version INTEGER NOT NULL, root TEXT, signature TEXT,"
    " extractor_version INTEGER NOT NULL DEFAULT 0)",
    "CREATE TABLE IF NOT EXISTS file_state("
    " rel_file TEXT PRIMARY KEY, size INTEGER NOT NULL, mtime INTEGER NOT NULL)",
    "CREATE TABLE IF NOT EXISTS stop_names("
    " name TEXT PRIMARY KEY)",
    "CREATE TABLE IF NOT EXISTS file_flags("
    " rel_file TEXT PRIMARY KEY, reason TEXT NOT NULL)",
    "CREATE INDEX IF NOT EXISTS idx_tags_kind_name ON tags(kind, name)",
    "CREATE INDEX IF NOT EXISTS idx_tags_file ON tags(file)",
    "CREATE INDEX IF NOT EXISTS idx_tags_rel_file ON tags(rel_file)",
]

_TagRow = Tuple[str, str, int, str, str]  # file, rel_file, line, name, kind


_SQLITE_MAGIC = b"SQLite format 3\x00"


def _looks_like_sqlite(path: str) -> bool:
    """True when path is missing/empty (sqlite can init it) or starts with
    the SQLite magic header.

    Guards DBStore against corrupt --db-path files: without it, sqlite
    raises a raw DatabaseError mid-init (scan path) or readers silently
    degrade to "no index" (diff path) — both dishonest about a file that
    exists but is unreadable.
    """
    try:
        with open(path, "rb") as f:
            head = f.read(len(_SQLITE_MAGIC))
    except OSError:
        return True  # missing/unreadable: let sqlite report it its own way
    return not head or head == _SQLITE_MAGIC


class DBStore:
    """Thin sqlite wrapper. Search/rank reads happen here; callers stay flat.

    read_only=True opens a frozen read-only view of an existing DB (used by
    --diff and tricorder_diff, which never update the index): no DDL, no
    migration, no commit — the connection itself rejects writes. Requires
    an existing path; the schema must already exist (readers fall back at
    query time for pre-version DBs, as get_meta does). A read-only open
    skips WAL sidecars (immutable=1), so uncheckpointed WAL rows are
    invisible — callers must point it at a closed/checkpointed DB."""

    def __init__(self, path: Optional[str] = None, *, read_only: bool = False):
        if read_only and not path:
            raise ValueError("read_only=True requires an existing DB path")
        if path and not _looks_like_sqlite(path):
            raise ValueError(
                f"Not a SQLite database: {path} "
                "(corrupt file, or the wrong --db-path?)")
        self.path = path
        self.read_only = read_only
        # check_same_thread=False: the scan runs via asyncio.to_thread (MCP
        # server) in a different thread than __init__; all access serialized
        # by self._lock.
        self._lock = threading.RLock()
        try:
            self._open_locked()
        except sqlite3.OperationalError:
            # Missing/unopenable file (e.g. read-only open of a nonexistent
            # DB): keep the original error contract — callers distinguish
            # "absent" from "corrupt".
            raise
        except sqlite3.DatabaseError as e:
            # Truncated/corrupt-but-magic-ok files slip past the header
            # check; sqlite only complains on first touch. Still a clean
            # error, never a raw traceback: callers (CLI/MCP) surface the
            # message as-is.
            try:
                self.conn.close()
            except Exception:
                pass
            raise ValueError(
                f"Not a SQLite database: {path or ':memory:'} ({e})") from e

    def _open_locked(self) -> None:
        path = self.path
        if self.read_only:
            # Frozen open: mode=ro&immutable=1 never creates the file or its
            # sidecars, so a read-only checkout can't crash on first DDL.
            self.conn = read_only_connect(path)
            return
        self.conn = sqlite3.connect(path if path else ":memory:", check_same_thread=False)
        # WAL keeps reads from blocking the walk's insert bursts on disk builds.
        # ponytail: DELETE for large existing DBs (>500MB) to avoid WAL loop;
        # WAL otherwise. Size-based, no repo names.
        try:
            is_large = bool(path) and os.path.getsize(path) > 500_000_000
        except OSError:
            is_large = False
        self.conn.execute(
            "PRAGMA journal_mode=DELETE" if is_large else ("PRAGMA journal_mode=WAL" if path else "PRAGMA journal_mode=MEMORY")
        )
        if path:
            # Tier 2: keep WAL bounded during large bulk loads (kotlin 69k)
            self.conn.execute("PRAGMA busy_timeout=30000")
            self.conn.execute("PRAGMA wal_autocheckpoint=1000")
            self.conn.execute("PRAGMA journal_size_limit=104857600")  # 100M

        for stmt in _DDL:
            self.conn.execute(stmt)
        # Migrate pre-version DBs: meta without extractor_version reads as
        # UNSTAMPED (0) downstream — never silently certify old tags.
        cols = {r[1] for r in self.conn.execute("PRAGMA table_info(meta)")}
        if "extractor_version" not in cols:
            self.conn.execute(
                "ALTER TABLE meta ADD COLUMN extractor_version INTEGER NOT NULL DEFAULT 0")
        self.conn.commit()

    # -- writes -------------------------------------------------------------
    def insert_tags(self, rows: Iterable[_TagRow]):
        """Bulk-insert one file's tags. Rows = (file, rel_file, line, name, kind)."""
        with self._lock:
            self._insert_tags_locked(rows)

    def _insert_tags_locked(self, rows: Iterable[_TagRow]):
        self.conn.executemany(
            "INSERT INTO tags(file, rel_file, line, name, kind) VALUES (?,?,?,?,?)",
            rows,
        )

    def reset(self):
        """Clear all rows: a fresh scan into an existing --db-path must not
        stack on top of previous runs. ponytail: full clear; per-file
        incremental recompute is Goal 6."""
        with self._lock:
            self.conn.execute("DELETE FROM tags")
            self.conn.execute("DELETE FROM refs")
            self.conn.execute("DELETE FROM meta")
            self.conn.execute("DELETE FROM file_state")
            self.conn.execute("DELETE FROM stop_names")
            self.conn.execute("DELETE FROM file_flags")
            self.conn.commit()

    def delete_tags_for_file(self, rel_file: str):
        """Remove all tags for one rel_file (incremental update)."""
        with self._lock:
            self.conn.execute("DELETE FROM tags WHERE rel_file=?", (rel_file,))
            self.conn.execute("DELETE FROM file_state WHERE rel_file=?", (rel_file,))

    def get_file_state(self) -> dict:
        """Return {rel_file: (size, mtime)} for incremental diff."""
        return {r[0]: (r[1], r[2]) for r in self.conn.execute("SELECT rel_file, size, mtime FROM file_state")}

    def set_file_state(self, rel_file: str, size: int, mtime: int):
        with self._lock:
            self.conn.execute(
                "INSERT OR REPLACE INTO file_state(rel_file, size, mtime) VALUES (?,?,?)",
                (rel_file, size, mtime),
            )

    def set_meta(self, root: str, signature: str, extractor_version: Optional[int] = None):
        """Replace (not append): meta holds exactly one row per DB.

        extractor_version=None preserves the stored stamp (incremental path:
        most tags were NOT re-extracted, so re-stamping would certify stale
        rows). Full scans pass EXTRACTOR_VERSION explicitly. Safe by default.
        """
        with self._lock:
            stored = self.conn.execute(
                "SELECT extractor_version FROM meta ORDER BY rowid DESC LIMIT 1"
            ).fetchone() if self._has_extractor_col() else None
            version = (extractor_version if extractor_version is not None
                       else (stored[0] if stored else 0))
            self.conn.execute("DELETE FROM meta")
            self.conn.execute(
                "INSERT INTO meta(schema_version, root, signature, extractor_version)"
                " VALUES (?,?,?,?)",
                (SCHEMA_VERSION, root, signature, version),
            )

    def _has_extractor_col(self) -> bool:
        return any(r[1] == "extractor_version"
                   for r in self.conn.execute("PRAGMA table_info(meta)"))

    def populate_refs(self):
        """Materialize refs edge table from def/ref tags (cross join on name).

        One row per (ref_file, def_file, name) that resolves; parallel edges for
        the same (ref, def) from different names stay distinct rows, so the
        multiplicity the MultiDiGraph used for ranking survives on disk.
        Uses rel_file (the graph's node identity).
        Idempotent: clears refs before repopulating (needed for incremental).
        """
        self.conn.execute("DELETE FROM refs")
        # ponytail: skip stop-names (def in >50 files) — unresolvable by name,
        # and their cross product is the 30M-edge bloat. Ceiling: fixed 50.
        self.conn.execute(
            "INSERT INTO refs(from_file, to_file, name) "
            "SELECT r.rel_file, d.rel_file, d.name "
            "FROM tags r JOIN tags d ON r.name = d.name "
            "WHERE r.kind='ref' AND d.kind='def' AND r.rel_file != d.rel_file "
            "AND d.name NOT IN (SELECT name FROM tags WHERE kind='def' "
            "GROUP BY name HAVING COUNT(DISTINCT rel_file) > 50)"
        )
        # Persist the skipped set so consumers can tell "no callers" apart
        # from "too common to resolve". Same predicate, same run.
        self.conn.execute("DELETE FROM stop_names")
        self.conn.execute(
            "INSERT INTO stop_names(name) "
            "SELECT name FROM tags WHERE kind='def' "
            "GROUP BY name HAVING COUNT(DISTINCT rel_file) > 50"
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

    def get_meta(self):
        """Latest (schema_version, root, signature, extractor_version).

        extractor_version 0 = pre-feature DB, staleness unknown. None if
        never scanned."""
        try:
            return self.conn.execute(
                "SELECT schema_version, root, signature, extractor_version FROM meta "
                "ORDER BY rowid DESC LIMIT 1"
            ).fetchone()
        except sqlite3.OperationalError:
            row = self.conn.execute(
                "SELECT schema_version, root, signature FROM meta "
                "ORDER BY rowid DESC LIMIT 1"
            ).fetchone()
            return (*row, 0) if row else None

    def stored_files(self):
        """Distinct rel_files with rows (cheap set for hit/subset checks)."""
        return {r[0] for r in self.conn.execute("SELECT DISTINCT rel_file FROM tags")}

    def count_tags_in(self, kind: str, rels) -> int:
        """Count kind='def'/'ref' tags restricted to the given rel_files."""
        rels = list(rels)
        if not rels:
            return 0
        q = f"SELECT COUNT(*) FROM tags WHERE kind=? AND rel_file IN ({','.join('?' * len(rels))})"
        return self.conn.execute(q, [kind, *rels]).fetchone()[0]

    def def_files(self) -> Iterator[str]:
        """rel_files with at least one kind='def' tag."""
        return (r[0] for r in self.conn.execute(
            "SELECT DISTINCT rel_file FROM tags WHERE kind='def'"))

    def is_stop_name(self, name: str) -> bool:
        """True if name was skipped by populate_refs (def in >50 files)."""
        return self.conn.execute(
            "SELECT 1 FROM stop_names WHERE name=?", (name,)).fetchone() is not None

    def get_stop_names(self) -> set:
        return {r[0] for r in self.conn.execute("SELECT name FROM stop_names")}

    def set_file_flag(self, rel_file: str, reason: str):
        """Record why a scanned file owns zero tags (no-grammar, empty, ...)."""
        with self._lock:
            self.conn.execute(
                "INSERT OR REPLACE INTO file_flags(rel_file, reason) VALUES (?,?)",
                (rel_file, reason),
            )

    def clear_file_flag(self, rel_file: str):
        with self._lock:
            self.conn.execute("DELETE FROM file_flags WHERE rel_file=?", (rel_file,))

    def get_file_flag(self, rel_file: str) -> Optional[str]:
        row = self.conn.execute(
            "SELECT reason FROM file_flags WHERE rel_file=?", (rel_file,)).fetchone()
        return row[0] if row else None

    def sync_file_flags(self, tagged: set, reasons: dict):
        """One-shot flag maintenance, called once per scan (not per file):
        record reasons for the tagless, then clear flags for anything
        tagged (tagged wins: a flag on a tagged file is stale)."""
        with self._lock:
            for rel, reason in reasons.items():
                self.conn.execute(
                    "INSERT OR REPLACE INTO file_flags(rel_file, reason) VALUES (?,?)",
                    (rel, reason),
                )
            if tagged:
                q = (f"DELETE FROM file_flags WHERE rel_file "
                     f"IN ({','.join('?' * len(tagged))})")
                self.conn.execute(q, list(tagged))
            self.conn.commit()

    def def_rows(self) -> Iterator[_TagRow]:
        """All def tags as (file, rel_file, line, name, 'def'), ordered like a file's tags."""
        return self.conn.execute(
            "SELECT file, rel_file, line, name, kind FROM tags "
            "WHERE kind='def' ORDER BY rel_file, line")

    def commit(self):
        self.conn.commit()

    def pagerank(
        self,
        nodes: Iterator[str],
        alpha: float = 0.85,
        max_iter: int = 100,
        tol: float = 1e-6,
        personalization: Optional[Dict[str, float]] = None,
    ) -> Dict[str, float]:
        """Compute PageRank via SQL power iteration on the refs table.

        Each iteration:
          1. Compute dangling-node mass (nodes with no outgoing edges).
          2. Distribute dangling mass proportionally to all nodes.
          3. For each node, sum incoming = sum(prev_rank / out_degree) from refs.
          4. new_rank = (1-alpha)/N + alpha * (incoming + dangling_share).

        All computation stays on-disk via SQL joins; only the final rank dict
        is materialized in RAM (one float per file node).

        ponytail: iterative SQL join — no in-memory graph. Ceiling: single
        table scan per iteration. Upgrade path: materialize a dangling table
        to avoid the dangling subquery.
        """
        with self._lock:
            node_list = list(nodes)
            n = len(node_list)
            if n == 0:
                return {}

            # Build a lookup table for fast personalization and node indexing.
            self.conn.execute("CREATE TEMP TABLE IF NOT EXISTS _pr_nodes(node TEXT PRIMARY KEY)")
            self.conn.execute("DELETE FROM _pr_nodes")
            self.conn.executemany("INSERT INTO _pr_nodes VALUES (?)", [(nd,) for nd in node_list])

            # Personalization table (optional).
            self.conn.execute("CREATE TEMP TABLE IF NOT EXISTS _pr_pers(node TEXT PRIMARY KEY, val REAL)")
            self.conn.execute("DELETE FROM _pr_pers")
            if personalization:
                self.conn.executemany(
                    "INSERT INTO _pr_pers VALUES (?, ?)",
                    [(nd, v) for nd, v in personalization.items() if nd in node_list],
                )

            # Initialize ranks uniformly.
            self.conn.execute("CREATE TEMP TABLE IF NOT EXISTS _pr_rank(node TEXT PRIMARY KEY, rank REAL)")
            self.conn.execute("DELETE FROM _pr_rank")
            init = 1.0 / n
            pers_init = self.conn.execute(
                "SELECT p.node, p.val FROM _pr_pers p JOIN _pr_nodes n ON p.node = n.node"
            ).fetchall()
            pers_map = {r[0]: r[1] for r in pers_init}
            self.conn.executemany(
                "INSERT INTO _pr_rank VALUES (?, ?)",
                [(nd, pers_map.get(nd, init)) for nd in node_list],
            )
            self.conn.commit()

            # Pre-compute out-degree for every node (needed for rank distribution).
            # COUNT(*) not COUNT(DISTINCT) to match nx.MultiDiGraph edge multiplicity.
            self.conn.execute("CREATE TEMP TABLE IF NOT EXISTS _pr_outdeg(node TEXT PRIMARY KEY, deg INTEGER)")
            self.conn.execute("DELETE FROM _pr_outdeg")
            self.conn.execute(
                "INSERT INTO _pr_outdeg SELECT n.node, COALESCE(c.c, 0) FROM _pr_nodes n "
                "LEFT JOIN (SELECT from_file AS node, COUNT(*) AS c FROM refs GROUP BY from_file) c "
                "ON n.node = c.node"
            )
            self.conn.commit()

            for _ in range(max_iter):
                # --- Step 1: dangling nodes (out-degree == 0) ---
                dangling_mass = self.conn.execute(
                    "SELECT COALESCE(SUM(rank), 0) FROM _pr_rank WHERE node IN "
                    "(SELECT node FROM _pr_outdeg WHERE deg = 0)"
                ).fetchone()[0]

                # --- Step 2: incoming rank per node ---
                # For each (to_file), sum(prev_rank / out_degree_of_from_file).
                self.conn.execute("CREATE TEMP TABLE IF NOT EXISTS _pr_incoming(node TEXT PRIMARY KEY, incoming REAL)")
                self.conn.execute("DELETE FROM _pr_incoming")
                self.conn.execute(
                    "INSERT INTO _pr_incoming "
                    "SELECT r.to_file, SUM(pr.rank / od.deg) "
                    "FROM refs r "
                    "JOIN _pr_rank pr ON r.from_file = pr.node "
                    "JOIN _pr_outdeg od ON r.from_file = od.node "
                    "GROUP BY r.to_file"
                )
                self.conn.commit()

                # --- Step 3: update ranks ---
                # new_rank = (1-alpha)/n + alpha * (incoming + dangling_share)
                dangling_share = dangling_mass / n if n else 0
                self.conn.execute("CREATE TEMP TABLE IF NOT EXISTS _pr_new(node TEXT PRIMARY KEY, rank REAL)")
                self.conn.execute("DELETE FROM _pr_new")
                self.conn.execute(
                    "INSERT INTO _pr_new "
                    "SELECT n.node, "
                    "  (1.0 - ?) / ? + ? * (COALESCE(i.incoming, 0.0) + ?) "
                    "FROM _pr_nodes n "
                    "LEFT JOIN _pr_incoming i ON n.node = i.node",
                    (alpha, n, alpha, dangling_share),
                )
                self.conn.commit()

                # --- Step 4: normalize (keep sum=1) and convergence check ---
                total = self.conn.execute(
                    "SELECT COALESCE(SUM(rank), 0) FROM _pr_new"
                ).fetchone()[0]
                if total > 0:
                    self.conn.execute(
                        "UPDATE _pr_new SET rank = rank / ?", (total,)
                    )
                diff = self.conn.execute(
                    "SELECT COALESCE(SUM(ABS(a.rank - b.rank)), 0) "
                    "FROM _pr_rank a JOIN _pr_new b ON a.node = b.node"
                ).fetchone()[0]
                self.conn.execute("DELETE FROM _pr_rank")
                self.conn.execute("INSERT INTO _pr_rank SELECT * FROM _pr_new")
                self.conn.commit()

                if diff < tol:
                    break

            # Materialize result.
            result = {
                row[0]: row[1]
                for row in self.conn.execute("SELECT node, rank FROM _pr_rank").fetchall()
            }

            # Cleanup temp tables.
            for tbl in ("_pr_nodes", "_pr_pers", "_pr_rank", "_pr_outdeg", "_pr_incoming", "_pr_new"):
                self.conn.execute(f"DROP TABLE IF EXISTS {tbl}")
            self.conn.commit()

            return result

    def checkpoint(self):
        """Force WAL checkpoint to truncate WAL (large bulk loads)."""
        try:
            self.conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            self.conn.commit()
        except Exception:
            pass

    def close(self):
        try:
            self.checkpoint()
            self.conn.commit()
        finally:
            self.conn.close()

    def mapped_rels(self) -> set:
        """Rel files the DB already covers (file_state keys). Read-only."""
        try:
            return set(self.get_file_state().keys())
        except Exception:
            return set()


def drop_mapped_files(files, root, db_path):
    """Drop walked files already mapped in the DB.

    Used after the --max-files prefix cap: files inside the prefix that
    are already indexed are skipped so a resumed rising-cap run doesn't
    re-parse them. Same-file helper for CLI + MCP (one implementation,
    no drift). No DB or any mapped set -> input unchanged.

    Rel comparison is case-normalized (os.path.normcase — identity on
    POSIX, lowercases on Windows): stored rels come from
    Tricorder.get_rel_fname (Path.relative_to, case-insensitive on
    Windows) while this loop computes rels via os.path.relpath
    (case-sensitive component compare on ntpath) against a
    realpath-resolved root — a case-mismatched root must still match.
    """
    if not db_path or not files:
        return files
    if not os.path.exists(db_path):
        # Never connect a possibly-absent DB (sqlite creates a 0-byte stub,
        # masking real absence); no DB means nothing is mapped.
        return files
    try:
        # Read-only: this helper only reads mapped_rels() (notably on the
        # CLI --diff path, where the target DB may be unwritable).
        db = DBStore(db_path, read_only=True)
        try:
            mapped = db.mapped_rels()
        finally:
            db.close()
    except Exception:
        return files
    if not mapped:
        return files
    norm = os.path.normcase
    mapped_n = {norm(m) for m in mapped}
    root_s = str(root)
    kept = []
    for f in files:
        try:
            # Same rel form as Tricorder.get_rel_fname (Path.relative_to):
            # os.path.relpath matches it on identical paths (backslashes).
            rel = os.path.relpath(os.path.realpath(f), root_s)
        except ValueError:
            kept.append(f)
            continue
        if norm(rel) not in mapped_n:
            kept.append(f)
    return kept


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