# DB and state model — what lives where, and what proves freshness

Source of truth: the code. Every claim below names its file.

The DB is the scan's memory. Everything incremental, resumable, and
freshness-checkable hangs off five sqlite tables plus two disk caches.
There is no server process and no daemon — state is files.

## 1. The sqlite DB (`database.py:DBStore`)

File-backed (`DBStore(path)`) or in-memory (`DBStore(None)`). Journal
mode is size-based: DELETE above 500MB, WAL otherwise
(`database.py:62-76`).

Tables (`database.py:30-47`):

| table | contents |
|---|---|
| `tags` | one row per tag: `(file, rel_file, line, name, kind)`, kind is `def`/`ref` |
| `refs` | one row per cross-file edge `(from_file, to_file, name)` |
| `meta` | exactly one row: `(schema_version, root, signature, extractor_version)` |
| `file_state` | per-file fingerprint `(rel_file, size, mtime)` — the dirty bit |
| `stop_names` | definition names in more than 50 files (see §3) |
| `file_flags` | why a scanned file owns zero tags (see §4) |

Reads stay flat: `count_tags_in`, `def_files`, `stored_files` are
single SELECTs. Only the final rank dict (one float per file) is ever
materialized in RAM.

### PageRank in SQL

`DBStore.pagerank()` (`database.py:286`): power iteration over `refs`
using temp tables (`_pr_nodes`, `_pr_rank`, `_pr_outdeg`), alpha 0.85,
100 iterations maximum, 1e-6 tolerance, optional personalization.
Dangling mass is redistributed each iteration. Out-degree uses
`COUNT(*)`, preserving `MultiDiGraph` edge multiplicity. One table
scan per iteration; no in-memory graph at any point.

## 2. Freshness, three layers

A file changed, the repo changed shape, or the extractor changed. A
different mechanism catches each:

1. **File changed** → `file_state`. Stored size or mtime differs →
   reparse that file only (`ranking.py:219-233`). Absent from
   `file_state` → not yet scanned → parse. Resume works the same
   way: each run picks up files the DB has never seen.
2. **Repo changed shape** → `meta.signature`. A stat hash over every
   included file's `(rel, size, mtime)`
   (`ranking._db_signature`, `ranking.py:98`).
3. **Extractor changed** → `meta.extractor_version`
   (`database.EXTRACTOR_VERSION`). The query-pack version that
   produced the tags. Full scans stamp it; incremental scans preserve
   it (`database.set_meta`). The default (no version argument)
   preserves, so partial work never certifies untouched rows.

Not covered: content changed with size and mtime identical
(`tricorder.py:46-49`).

## 3. Stop-names

`populate_refs()` (`database.py:133`) builds `refs` as one SQL join
but excludes names defined in more than 50 files: a bare name that
common cannot resolve a caller, and its cross product dominates the
edge table. The skipped set persists in `stop_names` so consumers can
distinguish "no callers" from "too common to resolve"
(`SymbolRecord.stop_note`, `utils.py:104`). The in-RAM cross-file
index applies the same guard (`graph.py:205-211`) so both paths agree.

## 4. file_flags

Synced in one place after every scan branch (`ranking.py:446+`):
`no-grammar`, `empty`, `parsed-zero-tags`, and similar — the
persisted form of `ParserMixin.untagged_reason()` (`parser.py:18`). A
zero-tag file is explained, never silent.

## 5. The two disk caches (not the DB)

- **Per-file tags cache** (`cache.py:TagsCacheMixin`): survives across
  processes. Identity includes repo path + `CACHE_VERSION` + config
  hash, so repos never share entries (`cache.py:38-59`).
- **Cross-ref bundle** (import index, defs/refs, per-file refs,
  `graph.py:44-100`): gated on a fingerprint of per-file mtimes mixed
  with `CACHE_VERSION` (`graph.py:27-42`). Same repo plus same code
  restores without re-parsing. Any index-logic change requires a
  `CACHE_VERSION` bump, or stale bundles keep serving.

Two version lineages, deliberately separate (`database.py:31-37`):
`EXTRACTOR_VERSION` for tag-producing changes (reparse required),
`CACHE_VERSION` for query-time and index changes (bundle drop is
enough). A query-time fix must never force a tag reparse, and the
reverse.

## 6. Where the DBs live

Canonical: `<root>/.tricorder/db/<name>.db` (`--init --root` prints
it). The MCP server tries that path first, then the central cache
(`tricorder_server._canonical_db_for`, `tricorder_server.py:198`).
`bench/coverage_audit.py` follows the same precedence and reports
which home it checked (`LOCAL` vs central).
