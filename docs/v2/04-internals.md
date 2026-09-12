# Internals — parse machinery, search, counting, reports

How the moving parts work under the flow in `01-pipeline.md`.

## Tree-sitter parsing (`parser.py`, `scm.py`)

- Grammars come from `grep-ast` (`grep_ast.tsl.get_language /
  get_parser`), cached per language in `_PARSER_CACHE` — one parser
  instance per language per process, not per file.
- Tag queries are `.scm` files shipped *inside the grep-ast package*
  (`scm.py:get_scm_fname` maps language → filename, e.g.
  `python-tags.scm`). There is no local queries directory; adding a
  language means grep-ast must ship its grammar + query.
- Captures split on `name.definition` → `def`, `name.reference` →
  `ref`; anything else (e.g. `reference.call`) is ignored for tags.
  Lines are 1-based (`start_point[0] + 1`).
- Skips, in order: unknown extension, missing grammar (warning naming
  the pack), missing `.scm`, empty/unreadable file, whitespace-only
  file (saves a `parse()` call — the bottleneck on huge repos),
  per-file wall-clock timeout (`TRICORDER_PARSER_TIMEOUT_S`, default
  5s). Any exception → warning + zero tags; the walk never stops.

## Parallelism

- Walk: bounded threaded discovery (`TRICORDER_WALK_WORKERS`, default
  min(8, cpu)) — I/O-bound, threads are correct.
- Parse: `ProcessPoolExecutor`, chunk 200 files, DB commit every 100
  (`ranking.py`). Workers = 2 when >15k files or >10k dirty, else
  min(4, cpu) — large repos go serial-ish to stay under the memory
  and CPU ceilings. Workers are pure (no DB handle); the parent
  commits.
- One scan process at a time per DB. Parallelism is *within* a run,
  never across runs.

## Pre-index probe (`ctags_probe.py`)

`--pre-index SYMBOL` narrows the walk before parsing, in layers:

1. `rg -l -w` with per-language `-g` globs — no index needed,
   sub-second even on kernel-scale trees. This is the primary path.
2. ctags index fallback (`ensure_ctags_index`), guarded: refuses to
   build over 20000 files, refuses to read a tags file over 100MB,
   7-day staleness, per-run timeout. The guards exist because a full
   tree ctags run once produced a 1.4GB artifact.

Probe hits become the file list; misses fall back to the normal walk
with a warning. Requires the `rg` binary on PATH.

## Import resolution (`import_parser.py`, `name_resolver.py`)

Per-language AST walkers extract `local_name → qualified_name →
source_file` bindings (one function per language, no framework).
`NameResolver` maps a bare referenced name in a given file to its
qualified target, with disambiguation across candidates. Feeds
`detail` (body + callers + callees) and graph `query` traversal —
not the file-level PageRank, which needs only name equality.

## Graph vs DB (`graph.py` vs `ranking.py`)

Two consumers of the same tags:

- File ranking uses SQL PageRank over `refs` (DB path) or the legacy
  `nx.MultiDiGraph` (`--no-db` only).
- Symbol navigation (detail body, callers/callees, `query()` DSL
  traversal, mermaid edges) uses `GraphMixin` structures built from
  tags on demand. The DB stores facts; the graph answers questions.
- Both enforce the >50-file stop-name guard (DB in `populate_refs`,
  index in `_build_cross_file_index`) so detail/query never show
  edges the ranker never had. `detail` reports the skip via
  `stop_note` instead of an empty callers list.
- The disk cross-ref bundle is fingerprinted on repo files **plus**
  `CACHE_VERSION` — index-logic changes invalidate old bundles.
- `detail` bodies come from `get_file_text`: whole-file text cached
  by mtime in the same diskcache as tags, so repeat lookups skip
  disk.

## Token counting (`utils.py:count_tokens`)

tiktoken, lazily imported (hard requirement when called — no silent
estimator). Unknown model names fall back to `cl100k_base`. The
`--model` flag selects the encoding; budget math (`--map-tokens`,
`--dry-run`, `repo_budget`) all flows through this one function.

## Reports (`report.py:FileReport`)

Every run returns counts: included/excluded (with reason per file),
definition/reference matches, files considered, `untagged_files`
(parsed but symbol-free), and `coverage_pct`. `exclude_unranked`
drops PageRank-0 files from the map; `filter_important_files`
(`importance.py`) keeps bloat out of the rendered tree.

## Write safety (`utils.py:safe_write`)

All in-process writes route through `safe_write`, which refuses
targets escaping the cache root. `--output` is the sole sanctioned
user-chosen path (explicit `allow_escape`).
