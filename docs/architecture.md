# Architecture

How tricorder turns a repository into a ranked, token-budgeted map.
For the `Class::method` naming rules specifically, see
[class-context-qualification](class-context-qualification.md).

## Scan pipeline

```
discover → parse → qualify → store → rank → render
```

1. **Discover** (`utils.discover_src_files`): walk `--root`, filter by
   extension (`utils.EXTENSIONS`, 28 languages), apply `--exclude-globs`,
   enforce the resource envelope (20k files / 500MB / depth 25 / 300s).
   `--pre-index SYMBOL` short-circuits this: rg-first file narrowing, no walk.
2. **Parse** (`ParserMixin.get_tags_raw`): tree-sitter per file (5s hard timeout
   each, `TRICORDER_PARSER_TIMEOUT_S`), one cached parser per language.
   Tree-sitter queries (`queries/`) extract definitions and references as
   `Tag(rel_fname, fname, line, name, kind)` tuples.
3. **Qualify** (`parser.qualify_with_class_context` + heuristic fallback):
   method definitions become `Class::method`. Identical in-process and in
   `ProcessPoolExecutor` workers. See the
   [deep dive](class-context-qualification.md).
4. **Store** (`database.DBStore`): tags/refs stream into sqlite — in-memory by
   default, `--db-path` for a file, `--init` for the canonical
   `<root>/.tricorder/db/<name>.db`. Stamped with `EXTRACTOR_VERSION`.
5. **Rank** (`ranking.RankingMixin`): PageRank over the reference graph, plus
   boosts for chat/mentioned files and identifiers. Binary search fits the
   top-ranked tags to `--map-tokens`.
6. **Render** (`render.py`): T0 (definitions only) or T1 (definitions + context
   lines) text map; or `--mermaid` flowchart; or `--format json`.

**Parallelism:** fresh scans use `ProcessPoolExecutor` at ≥200 files
(`_parse_worker` — pure, picklable, no DB handle in the worker); incremental
scans re-parse only dirty files (by `(size, mtime)` signature) and also go
parallel at ≥200 dirty files. Batch commits keep insert bursts cheap.

## Database design

`database.DBStore` — thin sqlite wrapper, all access under one `RLock`
(the MCP server scans via `asyncio.to_thread`).

| Table | Contents |
|---|---|
| `tags` | `(file, rel_file, line, name, kind)` — every definition. Indexed on `(kind, name)`, `file`, `rel_file`. |
| `refs` | `(from_file, to_file, name)` — reference edges for the rank graph. |
| `meta` | `(schema_version, root, signature, extractor_version)` — one row per scan. |
| `file_state` | `(rel_file, size, mtime)` — incremental invalidation. |
| `file_flags` | `(rel_file, reason)` — excluded/untagged bookkeeping. |
| `stop_names` | names excluded from ranking. |

Journal mode: `WAL` for file DBs (reads don't block insert bursts),
`DELETE` for DBs >500MB (avoids WAL growth loops), `MEMORY` for `:memory:`.

**Extractor versioning:** `EXTRACTOR_VERSION` (currently 2) is written to
`meta` on every scan. On open, a stamp mismatch means the extractor changed
since the DB was built → stored tags are stale regardless of file mtimes →
force a full rescan and re-stamp. Bump on **any** capture or qualification
change. Deliberately separate from `cache.CACHE_VERSION` (query-time bundles):
a query-time fix must not force tag reparse, and vice versa.

## Ranking

PageRank over the file/symbol reference graph (`networkx`), then:

- **Boosts:** `--chat-files` (highest) > `--mentioned-files` > `--mentioned-idents` > `--other-files`.
- **Budget fit:** binary search over the ranked tag list — the largest prefix
  fitting `--map-tokens` (tiktoken, `--model` encoding) wins.
- **`--exclude-unranked`** drops PageRank-0 files; **`--top N`** hard-caps tags.

## Call graph

`graph.py` builds the cross-file call graph:

- **Definitions index:** from `get_symbols()` records, keyed by (base) name.
- **Import resolution** (`import_parser.py`, `name_resolver.py`): per-language
  import statements map local names to defining modules, so `from a import b`
  correctly attributes cross-file calls. Produces dotted names (`pkg.mod.Class`).
- **Callers/callees:** `tricorder_detail` and the `tricorder_query` DSL
  (`callers('x') depth=2`, `callees('y')`, `refs('z')`) traverse it.
- **Persistence:** the import + cross-file indexes are serialized to the tags
  diskcache under `__cross_ref_index_v1__` with a fingerprint (sha256 over
  sorted `(rel path, mtime)`). Fresh MCP processes (one per RPC) restore them
  instead of re-parsing — any add/edit/delete invalidates the fingerprint and
  rebuilds. Best-effort: failures fall back to an in-memory rebuild.

## Caching

Three layers (TC-003 — a repo never controls cache state; automatic caches
stay outside the scanned repo):

1. **Tags diskcache** (`cache.TagsCacheMixin`): per-file tag bundles keyed by
   content signature, under `<tricorder workspace>/.tricorder/cache/`.
   Override the root with `TRICORDER_CACHE_HOME`.
2. **Cross-ref index bundle**: described above.
3. **Tag DB**: `:memory:` sqlite per scan; the pre-scan default persists to
   `<cache>/db/<name>.db` (outside the repo). Explicit `--init` instead
   creates the canonical DB at `<root>/.tricorder/db/<name>.db` — inside the
   project, like `.git`, so it travels with the checkout. Because it lives in
   the repo, `--init` is opt-in; nothing writes there implicitly.

Invalidation is stat-based (`{path}:{size}:{mtime}` sha256), not TTL.
`--signature-only` prints the 16-char signature the lifecycle plugin compares;
`--force-refresh` busts everything.

## Security model

Repository content is **untrusted input**. Controls:

| ID | Control | Behavior |
|---|---|---|
| TC-001 | Content boundary | Raw maps wrapped in `BEGIN/END UNTRUSTED REPOSITORY CONTEXT`. |
| TC-002 | Resource envelope | 20k files, 500MB, depth 25, 300s, 1MB/file → partial result + `scan_warning`. Tunable via `TRICORDER_MAX_*`. |
| TC-003 | Cache isolation | Automatic caches outside the repo; the opt-in `--init` DB lives at `<root>/.tricorder/db/` by design. |
| TC-004 | Parser timeout | 5s hard timeout per file (`TRICORDER_PARSER_TIMEOUT_S`); hangs are skipped. |
| TC-005 | Trust metadata | Every MCP response stamped `source: scanned_repository`, `trust: untrusted_repository_content`. |
| TC-006 | Path containment | `chat_files`/`detail` file params rejected outside `project_root`. |
| TC-007 | `max_files` clamp | MCP `max_files` clamped to 10,000 server-side; discovery early-stops at 20k. |
| TC-008 | Output containment | Server output under `get_cache_root()/.tricorder/output`; **all** in-process writes route through `utils.safe_write()`, which raises on any target escaping the cache root. `--output` is the sole sanctioned user-chosen path. |
| TC-009 | Dependency pinning | `requirements.txt` fully pinned; `scripts/depscan.py` emits inventory + `pip-audit`. |
| TC-010 | Parser fuzzing | `tests/security/` adversarial fixtures (deep nesting, huge lines, malformed, unicode, giant strings) assert no crash/hang. |

## Module map

| Module | Role |
|---|---|
| `tricorder.py` | CLI entry point, argparse, output wiring |
| `tricorder_server.py` | MCP server (fastmcp), 5 tools |
| `core.py` | `Tricorder` class — composes the mixins |
| `parser.py` | `ParserMixin` — tree-sitter extraction, qualification |
| `ranking.py` | `RankingMixin` — DB scan, PageRank, budget fit, workers |
| `database.py` | `DBStore` — sqlite schema, versioning |
| `graph.py` | `GraphMixin` — call graph, query DSL |
| `cache.py` | `TagsCacheMixin` — diskcache layer |
| `render.py` | Map rendering (T0/T1, mermaid, json) |
| `utils.py` | `Tag`, `SymbolRecord`, token counting, `safe_write`, language tables |
| `scm.py` | Tree-sitter query loading (two query packs) |
| `ctags_probe.py` | ctags/rg pre-index probe, language registry |
| `import_parser.py` / `name_resolver.py` | Import resolution for the call graph |
| `pre_scan.py` | Bulk pre-scan harness for many repos |
| `report.py` | `FileReport` — per-file scan accounting |
| `importance.py` | File importance filtering |
| `chunk_resume.py` | Resumable chunked operations |
