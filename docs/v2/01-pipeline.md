# Pipeline — what a scan technically does

Eight stages, in order. Code refs are `dev/db-map` as of Sep 2026.

## 1. Discovery (`utils.py:discover_src_files`)

Walks `--root`, keeps source files by extension, honors `.gitignore`
and `--exclude-globs`. Bounded by a resource envelope (file-count,
total-byte, depth, and time caps) — a hostile tree degrades to a
reported partial walk, never unbounded CPU. Threaded walk
(`TRICORDER_WALK_WORKERS`, default min(8, cpu)). With no positional
paths the CLI auto-scans `--root`; `find_git_root` resolves `.` to the
enclosing repo. Output is an ordered file list. Nothing parsed yet.

`--max-files N` (default 1000, `0` = uncapped) caps how many files
enter the run. `drop_mapped_files` (`database.py`) removes files
already in `file_state` first, so the cap limits *unmapped* files —
the sliding window that makes resume-by-rerun work.

## 2. Parse (`parser.py:ParserMixin.get_tags_raw`, `cache.py:get_tags`)

Per file: extension → grammar (`detect_lang`), tree-sitter parse via
`grep_ast.tsl` (parser cached per language; `.scm` tag queries ship
inside the grep-ast package — details in `04-internals.md`), `.scm`
query extracts
`Tag(rel_fname, fname, line, name, kind)` with kind `def` or `ref`.
Code is never executed. One bad file (missing grammar, binary junk,
pathological nesting) yields zero tags + a warning; the walk continues.

- Hard wall-clock bound per file: `TRICORDER_PARSER_TIMEOUT_S`
  (default 5, `core.py`).
- `cache.py:get_tags` sits in front: mtime-keyed diskcache hit skips
  parsing; a fixed `_SKIP_EXTS` set (`.frag`, `.vert`, `.cmake.in`,
  …) skips files that cannot hold symbols.
- Dirty-file parsing parallelizes: ProcessPool, chunk 200, batch
  commit 100; 2 workers past 15k files, else up to 4 (worker model in
  `04-internals.md`).
- `--pre-index SYMBOL` narrows giant trees *before* the walk:
  rg-first lookup, optional ctags index fallback, capped by
  `--pre-index-max-files` / `--pre-index-include-parents`.

## 3. Into the DB (`database.py:DBStore`)

Schema v1, six tables:

- `tags(file, rel_file, line, name, kind)` — one row per def/ref.
- `refs(from_file, to_file, name)` — materialized edges (stage 6).
- `meta(schema_version, root, signature)` — exactly one row.
- `file_state(rel_file, size, mtime)` — per-file stat fingerprint.
- `stop_names(name)` — def-names skipped by `populate_refs` (>50
  files), persisted so "no callers" vs "too common" stays answerable.
- `file_flags(rel_file, reason)` — why a scanned file owns zero tags
  (`no-grammar`, `no-query`, `empty`, `skip-ext`,
  `parsed-zero-tags`); synced once per scan, tagged files clear it.

One file's tags bulk-insert, then its AST is dropped — the walk never
holds the repo in RAM. `reset()` clears all six tables so reusing
`--db-path` never stacks. Journal mode is size-based, no repo names:
DELETE above 500MB, WAL below, MEMORY for `--no-db`.

`--no-db` opts out entirely into the legacy in-memory
`nx.MultiDiGraph` path (escape hatch for parity/debugging only).

## 4. Incremental / resume (`ranking.py:_get_ranked_tags_db`)

Each run diffs the walk against `file_state` (size+mtime per file).
Dirty files reparse; missing rows are new files (resume); unchanged
files are untouched. Committed batches survive kills, so resume is
just running again. First run against a populated DB with matching
signature prints `Pre-scan DB hit … skipping parse` and backfills
`file_state` for old DBs that lack it.

Freshness identity: `_db_signature` (sha1 of `rel:size:mtime` per
file, 16 hex chars) is stored in `meta.signature`; `--signature-only`
prints the same hash without building anything.

## 5. Refs (`database.py:populate_refs`)

Cross-joins every `ref` tag to same-named `def` tags in *other*
files: one row per `(ref_file, def_file, name)`. Names defined in
more than 50 files are skipped — unresolvable by name, and their
cross product is millions of garbage edges (kotlin `run`: tens of
millions → 0). Rebuilt from scratch each run (DELETE + INSERT):
idempotent by construction, verified by `test_db_invariants.py`.

## 6. Rank (`ranking.py`, `db.pagerank`)

SQL power-iteration PageRank over `refs` (alpha=0.85), nodes = all
included files. Personalization boosts chat/mentioned files — same
semantics as the legacy in-memory path. Ranks score *files*; tags
inherit their file's rank at render time.

## 7. Budget + render (`render.py`, `--map-tokens` default 8192)

Top-ranked tags fill the token budget. `--tier 0` emits definition
lines only (`context_lines == 0`, the "T0 mode" branch in `render.py`);
`--tier 1` adds ±`--context-lines` source lines per tag. `--full`
ignores the budget; with `--output` the map streams to a file handle
instead of RAM. `--format json` emits `{name, file, line, kind,
rank}` records; `--mermaid` renders the dependency flowchart.

## 8. Batch corpus builds (`pre_scan.py`)

Runs stages 1–7 per repo over a corpus dir: `--repos` selects,
`--extra` adds outside paths, `--dry-run` lists, per-repo timeout
3600s. Flags `--db-dir/--repos-dir/--tricorder` override the compiled
defaults. Bench/CI scaffolding — not the daily path (that's
`00-scan-first.md`).
