# Scan pipeline — what "scanning" does

Source of truth: the code. Every claim below names its file.

A scan turns a directory into queryable state in five stages:
`discover → parse → persist → rank → render`. No model calls, no
network. Tree-sitter, sqlite, and arithmetic.

## 1. Discover — which files count

`utils.discover_src_files()` (`utils.py:391`) is the single
implementation used by the CLI, the MCP server, the audit, and resume
logic.

- Skips: `.gitignore` contents (parsed per git root) +
  `_BUILTIN_SKIP_DIRS` (`utils.py:212`: node_modules, __pycache__,
  venv, env, build, dist, .tox, .eggs) + `vendor` + all
  dotfiles/dot-directories.
- Inclusion is not an extension allowlist: everything is included
  *except* skip sets (`_SKIP_EXTS`, `_BINARY_MEDIA_EXTS`,
  `_ARCHIVE_EXTS`, `_DATA_EXTS`) and files over
  `_MAX_SOURCE_FILE_SIZE` (1MB default).
- Resource envelope (`utils.py:424-430`): depth, file-count,
  total-bytes, and wall-clock budgets, overridable via `TRICORDER_*`
  env. Breaches land in the `report` dict as a `warning`.
- Threaded walk, deterministic sorted output (`utils.py:432-449`).

`--max-files` is a per-run budget on *unmapped* files, not a walk
prefix: `drop_mapped_files()` (`database.py:445`) removes
already-mapped paths *before* the cap applies, so repeated runs slide
forward through the tree.

## 2. Parse — tree-sitter to tags

`parser.py:ParserMixin`, three entry points over one mechanism:

- `get_tags_raw(fname, rel)` (`parser.py:116`): parse, run the
  language's `.scm` query, and convert captures to tags — every
  `name.definition.*` capture becomes a `def` tag, every
  `name.reference.*` capture a `ref` tag (`parser.py:168-191`). A `Tag`
  is `(rel_fname, fname, line, name, kind)`.
- `get_symbols(...)` (`parser.py:216`): definitions only, enriched
  into `SymbolRecord` — end line, signature (parameters plus return
  type, reconstructed per language, `parser.py:348-486`), docstring
  (first string in the body), language, tree-sitter kind. Methods in
  `::`-scoped languages get `Class::method` scoping
  (`parser.py:329-336`).
- `get_all_references(...)` (`parser.py:523`): identifier-only
  `@name.reference.*` captures (call, type, class, …). The bare
  `@reference.call` (whole expression) is ignored as noise.

Mechanics:

- Grammars come from `grep-ast` (`get_language`/`get_parser`), one
  cached parser per language (`_PARSER_CACHE`, `parser.py:11`).
- Hard 5-second wall-clock parse timeout in a daemon thread
  (`_parse_with_timeout`, `parser.py:81`;
  `TRICORDER_PARSER_TIMEOUT_S`). Timeout or error skips the file with
  a warning; parsing never fails the scan.
- Query files live in `queries/` (`scm.py:get_scm_fname`): first
  `queries/tree-sitter-language-pack/<lang>-tags.scm`, then
  `queries/tree-sitter-languages/`. A language with no query file
  produces no tags.
- Language detection (`utils.detect_lang`, `utils.py:569`):
  `grep-ast`'s `filename_to_lang`, a local table checked first, and a
  deliberate `.h → cpp` override (the cpp grammar is a strict
  superset of C).
- Empty files never reach the parser. `untagged_reason()`
  (`parser.py:18`) explains zero-tag files without parsing:
  skip-ext / empty / missing / no-grammar / no-query /
  parsed-zero-tags.

## 3. Persist — sqlite, incrementally

`database.py:DBStore`. Tables: `tags`, `refs`, `meta`, `file_state`,
`stop_names`, `file_flags` (schema in `database.py:9-20`).

- `file_state(rel_file, size, mtime)` is the dirty bit. A rescan
  re-parses only files whose stat changed or that are absent
  (`ranking.py:219-322`).
- `meta` holds one row: `(schema_version, root, signature,
  extractor_version)`. `signature` is a stat hash of the repo
  (`ranking._db_signature`, `ranking.py:98`). `extractor_version`
  (`database.EXTRACTOR_VERSION`) records which query-pack produced
  the tags: full scans stamp it, incremental scans preserve it
  (`database.set_meta`). A no-op scan cannot certify tags it did not
  touch.
- `populate_refs()` (`database.py:133`) materializes the cross-file
  edge table as one SQL join, excluding stop-names (definitions in
  more than 50 files, unresolvable by bare name). The skipped set
  persists in `stop_names`.
- `reset()` full-clears all tables: a fresh scan never stacks
  (`database.py:94`).
- `--wipe` (with `--init`) deletes the canonical DB first
  (`tricorder.py:296-300`). `--force-refresh` refreshes only the map
  render cache; it does not reparse.

Canonical home: `<cache>/db/<name>.db` (`--init --root`
prints it), where `<cache>` is `TRICORDER_CACHE_HOME` or
`<workspace>/.tricorder` — never inside the scanned repo. The MCP
server uses the same canonical path
(`tricorder_server._canonical_db_for`).

## 4. Rank — which tags survive the token budget

`ranking.py:RankingMixin`. Rank order comes from on-disk SQL
power-iteration PageRank over the `refs` graph. Mention boosts
(`--mentioned-files` / `--mentioned-idents`), important-file bias
(`importance.py`: READMEs, manifests, Dockerfiles, and similar), and
`exclude_unranked` / `exclude_untagged` filters shape the final set.

Output accounting rides in a `FileReport` (`report.py`): excluded
files with reasons, definition/reference counts, untagged list,
`coverage_pct`.

## 5. Render — tags to text

`render.py:to_tree` / `render_tree`: definition lines render
directly. Tier multiplies context lines (`tricorder.py`): tier 0 is
definition lines only with no file reads; tier 1 adds ±N source lines
per tag at one read each.

## Large trees

Cap each run (`--max-files`), compare `file_state` counts between
runs, continue while the count grows. Two consecutive zero-growth
runs mean stall (`chunk_resume.py` encodes this loop with DONE and
STALL exits). `bench/coverage_audit.py` checks completion:
disk-vs-`file_state` (did the cap finish?), `file_state`-vs-tags
(how much is tagless by nature), stacking, and extractor-staleness
flags. It reuses `discover_src_files`, so it cannot disagree with
the scanner about which files exist.
