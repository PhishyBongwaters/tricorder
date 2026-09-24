# CLI Reference

Complete reference for `tricorder`. See the [User Guide](user-guide.md) for
workflows and the [README](../README.md) for the quick start.

```
tricorder [paths ...] [options]
```

`paths` are files or directories to include in the map. If omitted, the
repository is auto-discovered from `--root`.

## Targeting

| Flag | Default | Description |
|---|---|---|
| `paths` | — | Files or directories to map. If omitted, auto-discover from `--root`. |
| `--root ROOT` | `.` | Repository root directory. |
| `--chat-files F ...` | — | Files currently being edited — highest ranking priority. |
| `--mentioned-files F ...` | — | Files explicitly mentioned — high priority. |
| `--mentioned-idents I ...` | — | Identifiers explicitly mentioned — boosts their ranking. |
| `--other-files F ...` | — | Other files to consider — lowest priority. |
| `--exclude-globs PATTERN ...` | — | POSIX globs (relative to `--root`) excluded from auto-scan, e.g. `vendor/** third_party/**`. Vendored subtrees are filtered *before* ranking so first-party code dominates. Ignored when explicit paths are given. |
| `--max-files N` | `0` (no cap) | Cap on files during auto-discovery when no paths are given. |

Priority order: `--chat-files` > `--mentioned-files` > `--other-files` > auto-discovered.

## Output control

| Flag | Default | Description |
|---|---|---|
| `--map-tokens N` | auto | Maximum tokens for the generated map. Unset (auto) scales with discovered repo size (`default_map_budget`: floor 2048, 0.5 tok/file, env-tunable); explicit N always wins, `0` skips the render. Binary search fits the highest-ranked tags to budget; the `Other files:` (untagged) section shares the same budget and truncates to a `+N more` tail instead of overflowing it. |
| `--tier {0,1}` | `0` | `0` = definitions only (~14 tokens/tag); `1` = definitions + context lines (~350 tokens/tag). |
| `--context-lines N` | `3` | Context lines around each definition when `--tier 1`. |
| `--top N` | — | Limit output to the top N ranked tags. |
| `--full` | off | Emit the full map regardless of token budget (disables truncation). |
| `--format {text,json}` | `text` | Output format. |
| `--output FILE` | — | Write map to file instead of stdout. |
| `--exclude-unranked` | off | Drop files with PageRank 0 from the map. |
| `--exclude-untagged` | off | Skip the `Other files:` section (files with no symbols). |
| `--mermaid` | off | Output the dependency graph as a Mermaid flowchart instead of a tag map. |
| `--mermaid-top N` | `30` | Limit the Mermaid graph to the top N nodes. |
| `--model NAME` | `gpt-4` | Model name used for token counting (tiktoken encoding). |
| `--max-context-window N` | — | Maximum context window size; adjusts the map token limit when no chat files are given. |
| `--quiet` | off | Suppress everything except the map (no verbose/info messages). |
| `--verbose` | off | Enable verbose logging. |

## Search modes (no map build)

These flags look things up without generating a map and exit immediately.
All honor `--format` (JSON output is machine-clean — no info lines).

| Flag | Default | Description |
|---|---|---|
| `--detect QUERY` | — | Identifier search, MCP `tricorder_detect` equivalent: definitions + references with file, line, context. |
| `--symbols QUERY` | — | Symbol search, MCP `tricorder_symbols` equivalent: name, type, file, line range, signature. |
| `--max-results N` | `5` (first pass) | Result cap for `--detect` / `--symbols`. First pass capped at 5 per v1.3; widen to 10 only when narrow pass returns nothing usable. `--detect` interleaves hits per file (round-robin) within each match tier before capping, so one file can't crowd out the rest. |
| `--max-tokens N` | — | Response budget for `--detect` / `--symbols`: trims per-hit context first (identity survives), then lowest-ranked hits. Unset = unbounded. |
| `--diff`, `--since` | off | Delta map: added/modified/deleted files since the last scan, plus tags for changed files. Read-only. `--since` is an alias for `--diff`. |
| `--smart-map QUERY` | — | **Smart MAP for repos <5000 files**: runs probe + ONE exact detect with QUERY. If exact match found, outputs detect results and SKIPS MAP; else falls through to full MAP. Combines probe+detect+conditional MAP in one call for agent ladder compliance (v1.6). |

```bash
tricorder /path/to/repo --detect authenticate --format json
tricorder /path/to/repo --symbols "test_" --max-results 20
tricorder /path/to/repo --diff          # what changed since the last --init scan?
tricorder /path/to/repo --smart-map "is_coll_manageable_by_user" --format json --quiet
```

## Pre-index probe (huge repos)

For a known symbol in a giant tree (kernel, monorepo), a full scan wastes
time walking every file. The probe runs **before** any path walk and is
authoritative.

| Flag | Default | Description |
|---|---|---|
| `--pre-index SYMBOL` | — | Narrow the scan to files containing SYMBOL. rg-first (`rg -l -w` with multi-language globs); ctags fallback only if rg finds nothing. Ctags index builds are refused on >20,000 source files; >100MB existing tag files are skipped (rg-only fallback), not treated as corrupt. |
| `--pre-index-max-files N` | `100` | Cap on files pulled in from probe results. |
| `--pre-index-include-parents N` | `0` | Also include N parent directories of matched files. |

Pick a **specific** symbol: `pick_next_task` (~6 matches) lands on `kernel/sched/`;
`schedule` (thousands of matches) caps out and misses. Example:

```bash
tricorder /path/to/linux --pre-index "pick_next_task" --pre-index-max-files 20 --map-tokens 2048
# kernel/sched/ narrowed in ~1.1s, no full-tree walk
```

Requires `rg` on `PATH` for the fast path.

## Database

DB-backed scanning is the **default**: tags/refs stream into sqlite instead of
being held in RAM. See [Architecture](architecture.md#scan-pipeline).

| Flag | Description |
|---|---|
| `--db-path PATH` | Persist per-file tags/refs to this sqlite file instead of in-memory sqlite. |
| `--no-db` | Opt out: use the legacy in-memory `nx.MultiDiGraph` path. Escape hatch for parity/debugging. Mutually exclusive with `--db-path`. |
| `--init` | Create/open the canonical DB at `<root>/.tricorder/db/<name>.db`, print its path, exit. Idempotent; never wipes without `--wipe`. |
| `--wipe` | With `--init` only: delete the existing canonical DB first. (`--wipe` requires `--init`.) Stop the MCP server first if it is running against this DB — wiping under a held-open DB fails cleanly on Windows, and on POSIX the server detects the replacement and rebuilds. |
| `--db-coverage` | Print one-line mapped-DB coverage for `--root` (`mapped: N files, M tags, db sig X`) and exit. Prints nothing when unmapped. |

## Diagnostics

| Flag | Description |
|---|---|
| `--dry-run` | Estimate the token budget without generating the map. |
| `--signature-only` | Print the 16-char stat-based content signature and exit. No map is built. Used by the lifecycle plugin for cache validation. |
| `--stats-only [MAP_FILE]` | Print token-budget JSON for `--root` and exit: `{token_estimate, full_repo_estimate, savings_pct}`. No map is built. |
| `--probe-digest` | Print the turn-0 probe digest (language tally + sizes + navigation hint) for `--root` and exit. No map build, no token budget — cheap even on huge repos. This is the digest the Hermes/DSH plugins fall back to when the project isn't pre-mapped (a pre-mapped project instead gets a coverage/steering line from its DB). |
| `--force-refresh` | Force refresh of caches. |
| `--help` | Print the full option list and exit. |

## Examples

```bash
tricorder .                                   # Map current directory
tricorder src/ --map-tokens 2048              # Map src/ with a 2048-token budget
tricorder file1.py file2.py                   # Map specific files
tricorder --chat-files main.py --other-files src/
tricorder . --tier 1 --context-lines 5        # Definitions + 5 lines context
tricorder . --mermaid --mermaid-top 30        # Dependency flowchart
tricorder . --exclude-globs 'vendor/**' 'third_party/**'
tricorder . --dry-run --map-tokens 2048       # Budget estimate only
tricorder . --top 10 --format json             # Top 10 tags as JSON
```

## Exit behavior

- On success the map (or requested diagnostic) goes to stdout; `--output` writes to a file instead.
- `--quiet` guarantees stdout contains *only* the map — safe for piping.
- Resource limits (depth 25, 1MB per file by default; file count, total
  bytes, scan time unlimited unless capped via `TRICORDER_MAX_*` — see
  [Architecture](architecture.md#security-model)) produce a partial result plus
  a warning on stderr (MCP responses carry a `scan_warning` field),
  never a silent truncation.
