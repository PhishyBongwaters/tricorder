# Scan pipeline — what "scanning" actually does

Source of truth: the code. Every claim below names its file.

A scan turns a directory into queryable state in five stages:
`discover → parse → persist → rank → render`. Nothing calls a model;
everything is tree-sitter, sqlite, and arithmetic.

## 1. Discover — which files count

`utils.discover_src_files()` (`utils.py:391`) is the single implementation —
the CLI, the MCP server, the audit, and resume logic all call it. No drift.

- Skips: `.gitignore` contents (parsed per git root) + `_BUILTIN_SKIP_DIRS`
  (`utils.py:212`: node_modules, __pycache__, venv, env, build, dist, .tox,
  .eggs) + `vendor` + all dotfiles/dot-directories.
- Not an extension allowlist: everything is included *except* skip sets
  (`_SKIP_EXTS`, `_BINARY_MEDIA_EXTS`, `_ARCHIVE_EXTS`, `_DATA_EXTS`) and
  files over `_MAX_SOURCE_FILE_SIZE` (1MB default).
- Resource envelope (`utils.py:424-430`): depth, file-count, total-bytes,
  and wall-clock budgets, all overridable via `TRICORDER_*` env. Breaches
  land in the `report` dict as a `warning`, never silent truncation.
- Threaded walk on Windows (directory listing is latency-bound),
  deterministic sorted output (`utils.py:432-449`).

`--max-files` is a per-run budget on *unmapped* files, not a walk prefix:
`drop_mapped_files()` (`database.py:445`) removes already-mapped paths
*before* the cap applies, so reruns slide forward. Verified live on swift:
caps 5000 → 10000 → 15000 produced 5000 → 15000 → 30000 rows.

## 2. Parse — tree-sitter to tags

`parser.py:ParserMixin`, three entry points over one mechanism:

- `get_tags_raw(fname, rel)` (`parser.py:116`): parse → run the language's
  `.scm` query → every `name.definition.*` capture becomes a `def` tag,
  every `name.reference.*` capture a `ref` tag (`parser.py:168-191`).
  A `Tag` is just `(rel_fname, fname, line, name, kind)`.
- `get_symbols(...)` (`parser.py:216`): definitions only, enriched into
  `SymbolRecord` — end line, signature (params + return type reconstructed
  per language, `parser.py:348-486`), docstring (first string in body),
  language, tree-sitter kind. C++-style methods get `Class::method`
  scoping (`parser.py:329-336`).
- `get_all_references(...)` (`parser.py:523`): identifier-only
  `@name.reference.*` captures (call, type, class, …). The bare
  `@reference.call` (whole expression) is deliberately ignored as noise.

Mechanics that matter:

- Grammars come from `grep-ast` (`get_language`/`get_parser`), one cached
  parser per language (`_PARSER_CACHE`, `parser.py:11`).
- Hard 5s wall-clock parse timeout in a daemon thread
  (`_parse_with_timeout`, `parser.py:81`; `TRICORDER_PARSER_TIMEOUT_S`).
  Timeout/error → file skipped with a warning, never fatal.
- Query files live in `queries/` (`scm.py:get_scm_fname`): first
  `queries/tree-sitter-language-pack/<lang>-tags.scm`, then
  `queries/tree-sitter-languages/`. No query file → no tags, silently.
- Language detection (`utils.detect_lang`, `utils.py:569`): `grep-ast`'s
  `filename_to_lang` plus a local table checked first, plus a deliberate
  `.h → cpp` override (cpp grammar is a strict superset of C).
- Empty/whitespace files never reach the parser. `untagged_reason()`
  (`parser.py:18`) explains zero-tag files without parsing:
  skip-ext / empty / missing / no-grammar / no-query / parsed-zero-tags.

## 3. Persist — sqlite, incrementally

`database.py:DBStore`. Tables: `tags`, `refs`, `meta`, `file_state`,
`stop_names`, `file_flags` (schema in `database.py:9-20`).

- `file_state(rel_file, size, mtime)` is the dirty bit. A rescan re-parses
  only files whose stat changed or that are absent (the resume path,
  `ranking.py:219-322`). Unchanged files are cache hits — which is why a
  plain rescan does *not* refresh tags after a query-pack change.
- `meta` holds one row: `(schema_version, root, signature,
  extractor_version)`. `signature` is a stat hash of the repo
  (`ranking._db_signature`, `ranking.py:98`). `extractor_version`
  (`database.EXTRACTOR_VERSION`) records which query-pack produced the
  tags: full scans stamp it (`ranking.py:197,218,381,440`), incremental
  scans preserve it (`ranking.py:320`). The audit flags `UNSTAMPED` (0)
  and `STALE-vN`.
- `populate_refs()` (`database.py:133`) materializes the cross-file edge
  table as one SQL join, skipping stop-names (defs in >50 files —
  unresolvable by name, and their cross product was the 30M-edge bloat).
- `reset()` full-clears all tables: a fresh scan never stacks
  (`database.py:94`).
- `--wipe` (with `--init`) deletes the canonical DB first
  (`tricorder.py:296-300`). `--force-refresh` only refreshes the map
  render cache — it does *not* reparse.

Canonical home: `<root>/.tricorder/db/<name>.db` (`--init --root` prints
it). The MCP server prefers it, falling back to the central cache
(`tricorder_server._canonical_db_for`, `tricorder_server.py:198`).

## 4. Rank — which tags survive the token budget

`ranking.py:RankingMixin`. Rank order comes from on-disk SQL
power-iteration PageRank over the `refs` graph (no whole-repo
`nx.MultiDiGraph` in RAM — that was the memory blowup this replaced).
Mention boosts (`--mentioned-files/--mentioned-idents`), important-file
bias (`importance.py`: READMEs, manifests, Dockerfiles…), and
`exclude_unranked`/`exclude_untagged` filters shape the final set.

Output accounting rides in a `FileReport` (`report.py`): excluded files
with reasons, def/ref counts, untagged list, `coverage_pct`.

## 5. Render — tags to text

`render.py:to_tree` / `render_tree`: definition lines render directly.
Tier is a multiplier on context lines (`tricorder.py`: tier 0 = def lines
only, no file reads; tier ≥1 = ±N source lines per tag, one read each).

## Large-repo protocol (verified, not theory)

- One `--max-files N` run at a time (5000 is the working default),
  verify `file_state`/tags/refs counts between chunks, next chunk only
  when the previous grew. Two consecutive zero-growth chunks = STALL.
- `chunk_resume.py` automates the loop; the standing rule is manual
  single chunks with a ping per chunk. Never unsupervised loops.
- `bench/coverage_audit.py` is the instrument: disk-vs-`file_state`
  (did the cap finish?) and `file_state`-vs-tags (how much is
  tagless-by-nature?), plus stacking and extractor-staleness flags.
  It reuses `discover_src_files` so it cannot disagree with the scanner.
