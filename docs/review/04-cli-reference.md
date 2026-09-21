# CLI reference — the command line, by task

Source of truth: `python tricorder.py --help`. Every flag below is
quoted or faithfully condensed from it. The agent-facing surface is
documented separately (`03-agent-retrieval.md`).

## Map something

```
tricorder.py .                                    # map current directory
tricorder.py src/ --map-tokens 2048               # tighter budget
tricorder.py file1.py file2.py                    # specific files
tricorder.py --chat-files main.py --other-files src/
```

- `paths`, `--chat-files`, `--other-files`: what goes in. Chat files
  rank highest, then `--mentioned-files` / `--mentioned-idents`,
  then everything else.
- `--map-tokens` (default 8192): the budget. `--top N` caps output
  tags. `--full` disables truncation (for indexing to disk).
- `--tier {0,1}` (default 0): 0 is definitions only with no file
  reads; 1 adds ± `--context-lines` (default 3) at one read per tag.
- `--format {text,json}`, `--mermaid` / `--mermaid-top N` (default
  30 nodes), `--output FILE` (map to disk instead of stdout),
  `--quiet` (map only, no chatter).
- `--model` (default gpt-4): whose tokenizer counts the budget.
- `--exclude-unranked`: drop PageRank-0 files. `--exclude-untagged`:
  drop the untagged-files section. `--exclude-globs PATTERN ...`
  (e.g. `vendor/**`): cut third-party subtrees before ranking.

## Inspect without building

- `--dry-run`: price the map (tag count, tokens per tag, tags at
  budget, full-repo estimate). No map built.
- `--stats-only [MAP_FILE]`: token-budget JSON for `--root`
  (`token_estimate`, `full_repo_estimate`, `savings_pct`). No map
  built.
- `--signature-only`: 16-hex-char stat signature, exit. Cache
  validation.
- `--probe-digest`: turn-0 digest (language tally, sizes, navigation
  hint). No map, no budget. Same text the Hermes/DSH plugins inject.
- `--db-coverage`: one-line mapped-DB coverage for `--root`, exit.
  Silent when unmapped.
- `--diff` / `--since`: delta map — added/modified/deleted files since the last
  scan, plus tags for changed files. Read-only; honors `--format`.
- `--detect QUERY` / `--symbols QUERY`: identifier/symbol search
  without a map build (MCP `tricorder_detect` / `tricorder_symbols`
  equivalents). `--max-results N` (default 10) caps results; both
  honor `--format` with machine-clean JSON.

## Persist and reset

- `--db-path PATH`: persist tags/refs to this sqlite file. DB-backed
  scanning is the default; this chooses file over `:memory:`.
  `--no-db` opts out to the legacy in-memory graph (mutually
  exclusive with `--db-path`).
- `--init`: create or open the canonical
  `<root>/.tricorder/db/<name>.db`, print its path, exit. Idempotent;
  never wipes without `--wipe`.
- `--wipe` (with `--init` only): delete the canonical DB first.
- `--force-refresh`: refreshes the map render cache. Does not
  reparse.

## Narrow giant trees

- `--pre-index SYMBOL`: find files mentioning the symbol first,
  scan only those. `--pre-index-max-files` (default 100),
  `--pre-index-include-parents N`.
- `--max-files N` (default 0 = unlimited): per-run budget on
  *unmapped* files — already-mapped files are dropped before the cap
  applies, so repeated runs advance through the tree.

## Companion scripts

- `chunk_resume.py <repo> [--start-cap N] [--step N]`: rising-cap
  loop to full coverage; exits DONE when mapped equals discovered,
  STALL on two consecutive zero-growth chunks.
- `pre_scan.py`: scan every repo under a directory into the central
  cache (`--repos-dir`, `--extra`, `--dry-run`).
- `bench/coverage_audit.py [repo]`: completion audit —
  disk-vs-`file_state`, `file_state`-vs-tags, stacking,
  extractor-staleness (`UNSTAMPED` / `STALE-vN`), and which DB home
  was checked (`LOCAL` vs central).
- `bench/coverage_audit.py --stamp <repo>...`: record a human
  verification that a DB's tags are current. Never automatic.

## Environment knobs

`TRICORDER_PARSER_TIMEOUT_S` (default 5): per-file parse ceiling.
`TRICORDER_MAX_SCAN_FILES` / `TRICORDER_MAX_TOTAL_BYTES` /
`TRICORDER_MAX_SCAN_DEPTH` / `TRICORDER_MAX_SCAN_TIME_S` /
`TRICORDER_MAX_SOURCE_FILE_SIZE` (default 1MB): discovery envelope.
`TRICORDER_WALK_WORKERS`: walk parallelism.
`TRICORDER_CACHE_HOME`: relocate the disk cache.
