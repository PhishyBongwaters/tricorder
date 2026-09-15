# DB and state model — what lives where, and what proves freshness

Source of truth: the code. Every claim below names its file.

One sentence: the DB is the scan's memory. Everything incremental,
resumable, and freshness-checkable hangs off five sqlite tables plus two
disk caches. There is no server process and no daemon — state is files.

## 1. The sqlite DB (`database.py:DBStore`)

Created file-backed (`DBStore(path)`) or in-memory (`DBStore(None)`).
Journal mode is size-based, no repo names: DELETE above 500MB, WAL
otherwise (`database.py:62-76`).

Tables (`database.py:30-47`):

| table | contents |
|---|---|
| `tags` | one row per tag: `(file, rel_file, line, name, kind)`, kind is `def`/`ref` |
| `refs` | one row per cross-file edge `(from_file, to_file, name)` |
| `meta` | exactly one row: `(schema_version, root, signature, extractor_version)` |
| `file_state` | per-file fingerprint `(rel_file, size, mtime)` — the dirty bit |
| `stop_names` | def-names in >50 files, unresolvable by name (see §3) |
| `file_flags` | why a scanned file owns zero tags (see §4) |

Reads stay flat: `count_tags_in`, `def_files`, `stored_files` are all
single SELECTs (`database.py:184-281`). Only the final rank dict (one
float per file) is ever materialized in RAM.

### PageRank lives in SQL too

`DBStore.pagerank()` (`database.py:286`): power iteration over `refs`
with temp tables (`_pr_nodes`, `_pr_rank`, `_pr_outdeg`), alpha 0.85,
max 100 iterations, tolerance 1e-6, optional personalization. Dangling
mass redistributed per iteration. Out-degree uses `COUNT(*)` (not
distinct) to preserve `MultiDiGraph` edge multiplicity. One table scan
per iteration; no in-memory graph at any point.

## 2. Freshness, three layers

Something changed in the repo, in the extractor, or in the query logic.
A different mechanism catches each:

1. **File changed** → `file_state`. Size or mtime differs from the stored
   fingerprint → reparse that file only (`ranking.py:219-233`). Missing
   from `file_state` → not yet scanned → parse (this is also how chunk
   resume works: each run picks up where the last stopped).
2. **Repo changed shape** → `meta.signature`. A stat hash over every
   included file's `(rel, size, mtime)` (`ranking._db_signature`,
   `ranking.py:98`). Cheap tripwire for add/edit/delete.
3. **Extractor changed** → `meta.extractor_version`
   (`database.EXTRACTOR_VERSION`). The query-pack version that produced
   the tags. Full scans stamp it; incremental scans preserve it
   (`database.set_meta`, `database.py:138`; call sites
   `ranking.py:197,218,320,381,440` — only post-`reset()` paths stamp).
   Safe default: `set_meta` with no version argument never upgrades the
   stamp, so a no-op scan cannot certify tags it didn't touch.

What none of them catch: content changed with size+mtime identical
(practically never — `tricorder.py:46-49`).

## 3. Stop-names: precision the ranker never had, removed

`populate_refs()` (`database.py:133`) builds `refs` as one SQL join but
excludes names defined in >50 files. A bare name occurring in that many
files cannot resolve a caller, and its cross product was a 30M-edge
blowup (kotlin's `run` alone). The skipped set persists in `stop_names`
so consumers can tell "no callers" apart from "too common to resolve"
(`SymbolRecord.stop_note`, `utils.py:104`). The in-RAM cross-file index
mirrors the guard (`graph.py:205-211`) so both paths agree.

## 4. file_flags: why a file owns zero tags

Synced in one place after every scan branch (`ranking.py:446+`):
`no-grammar`, `empty`, `parsed-zero-tags`, etc. — the persisted form of
`ParserMixin.untagged_reason()` (`parser.py:18`). A zero-tag file is
explained, never silent.

## 5. The two disk caches (not the DB)

- **Per-file tags cache** (`cache.py:TagsCacheMixin`, dir
  `.tricorder.tags.cache.v{CACHE_VERSION}`): survives across processes.
  Identity includes repo path + `CACHE_VERSION` + config hash, so repos
  never share and one repo can't poison another's (`cache.py:38-59`).
- **Cross-ref bundle** (import index + defs/refs + per-file refs,
  `graph.py:44-100`): gated on a fingerprint of per-file mtimes mixed
  with `CACHE_VERSION` (`graph.py:27-42`). Same-repo, same-code →
  restore without re-parsing. Any index-logic change must bump
  `CACHE_VERSION` or stale bundles keep serving (this bit once: #46
  landed without a bump).

Two version lineages, deliberately separate (`database.py:31-37`):
`EXTRACTOR_VERSION` for tag-producing changes (reparse needed),
`CACHE_VERSION` for query-time/index changes (bundle drop is enough).
A query-time fix must never force a tag reparse, and vice versa.

## 6. Where the DBs live

Canonical: `<root>/.tricorder/db/<name>.db` (`--init --root` prints it).
The MCP server tries that first, then the central cache
(`tricorder_server._canonical_db_for`, `tricorder_server.py:198`).
`bench/coverage_audit.py` follows the same precedence and flags which
home it checked (`LOCAL` vs central).
