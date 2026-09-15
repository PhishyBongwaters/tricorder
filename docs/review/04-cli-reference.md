# CLI reference — the command line, by task

Source of truth: `python tricorder.py --help`. Every flag below is
quoted or faithfully condensed from it. For the agent-facing surface,
see `03-agent-retrieval.md` — the CLI is the secondary interface.

## Map something

```
tricorder.py .                                    # map current directory
tricorder.py src/ --map-tokens 2048               # tighter budget
tricorder.py file1.py file2.py                    # specific files
tricorder.py --chat-files main.py --other-files src/
```

- `paths`, `--chat-files`, `--other-files`: what goes in. Chat files
  rank highest, then mentioned files/idents (`--mentioned-files`,
  `--mentioned-idents`), then everything else.
- `--map-tokens` (default 8192): the budget. `--top N` caps output tags.
  `--full` disables truncation (for indexing to disk, not for reading).
- `--tier {0,1}` (default 0): 0 = definitions only, no file reads;
  1 = definitions ± `--context-lines` (default 3), one read per tag.
- `--format {text,json}`, `--mermaid` / `--mermaid-top N` (default 30
  nodes), `--output FILE` (write the map to disk instead of stdout),
  `--quiet` (map only, no chatter).
- `--model` (default gpt-4): whose tokenizer counts the budget.
- `--exclude-unranked`: drop PageRank-0 files. `--exclude-untagged`:
  drop the untagged-files section. `--exclude-globs PATTERN ...`
  (e.g. `vendor/**`): cut third-party subtrees before ranking.

## Inspect without building

- `--dry-run`: price the map (tag count, tokens per tag, tags at
  budget, full-repo estimate). No map built.
- `--stats-only [MAP_FILE]`: token-budget JSON for `--root`
  (`token_estimate`, `full_repo_estimate`, `savings_pct`). No map built.
- `--signature-only`: 16-hex-char stat signature, exit. Cache validation.
- `--probe-digest`: turn-0 digest (language tally, sizes, navigation
  hint). No map, no budget — cheap on huge repos. Same text the
  Hermes/DSH plugins inject.
- `--db-coverage`: one-line mapped-DB coverage for `--root`, exit.
  Silent when unmapped.

## Persist and reset

- `--db-path PATH`: persist tags/refs to this sqlite file (flat-memory
  walk). DB-backed scanning is the default; this only chooses file over
  `:memory:`. `--no-db` opts out to the legacy in-memory graph
  (parity/debugging hatch, mutually exclusive with `--db-path`).
- `--init`: create/open the canonical `<root>/.tricorder/db/<name>.db`,
  print its path, exit. Idempotent; never wipes without `--wipe`.
- `--wipe` (with `--init` only): delete the canonical DB first.
- `--force-refresh`: refreshes the map render cache. Does *not* reparse.

## Narrow giant trees

- `--pre-index SYMBOL`: find files mentioning the symbol first (ctags
  index or `rg`), scan only those. `--pre-index-max-files` (default
  100), `--pre-index-include-parents N`.
- `--max-files N` (default 0 = unlimited): per-run budget on *unmapped*
  files — already-mapped files don't count (sliding window). Reruns
  advance; two consecutive zero-growth runs mean stall.

## Companion scripts (bench/ and root)

- `chunk_resume.py <repo> [--start-cap N] [--step N]`: serial
  rising-cap loop to full coverage; stops at DONE or two-stall.
  The manual protocol is single `--max-files` runs with count checks
  between — the script is the automated form.
- `pre_scan.py`: scan every repo under a directory into the central
  cache (`--repos-dir`, `--extra` for outsiders like projectm,
  `--dry-run` to list). One home per repo still applies: the MCP
  server prefers `<root>/.tricorder/db/` over central.
- `bench/coverage_audit.py [repo]`: the instrument. Disk-vs-`file_state`
  (did the cap finish?), `file_state`-vs-tags (tagless-by-nature count),
  stacking, extractor-staleness (`UNSTAMPED` / `STALE-vN`), and which
  DB home it checked (`LOCAL` vs central).
- `bench/coverage_audit.py --stamp <repo>...`: human assertion that a
  DB's tags are current. Never automatic.

## Environment knobs

`TRICORDER_PARSER_TIMEOUT_S` (default 5): per-file parse ceiling.
`TRICORDER_MAX_SCAN_FILES` / `TRICORDER_MAX_TOTAL_BYTES` /
`TRICORDER_MAX_SCAN_DEPTH` / `TRICORDER_MAX_SCAN_TIME_S` /
`TRICORDER_MAX_SOURCE_FILE_SIZE` (default 1MB): discovery envelope.
`TRICORDER_WALK_WORKERS`: walk parallelism.
`TRICORDER_CACHE_HOME`: move the disk cache off the default home.
