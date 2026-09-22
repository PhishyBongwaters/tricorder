---
name: codebase-tricorder
description: Use tricorder to map a codebase (symbols, call graphs, signatures) without reading every file. Highest-value when exploring an unfamiliar repo, locating a definition, or summarizing structure.
---

# Tricorder

Use tricorder when you need `symbols`, `signatures`, `callers/callees`, or a compact **map** of a codebase without reading every file. It scans with tree-sitter, ranks by PageRank, and returns only the important definitions — typically **~1.5% of full-repo token cost**.

It is surfaced two ways:

- **Native MCP tools** (primary): when tricorder is registered as an MCP server, its tools appear as `mcp__tricorder__tricorder_scan`, `mcp__tricorder__tricorder_detect`, `mcp__tricorder__tricorder_symbols`, `mcp__tricorder__tricorder_detail`, `mcp__tricorder__tricorder_query`, `mcp__tricorder__tricorder_diff`, `mcp__tricorder__tricorder_locate`.
- **CLI**: `tricorder . --map-tokens <N>` for ad-hoc runs without the MCP server.

## When to use

| Situation | Use |
|-----------|-----|
| "How is this project structured?" | `mcp__tricorder__tricorder_scan` (text) |
| Module/component dependency view | `mcp__tricorder__tricorder_scan` with `output_format: mermaid` |
| "Where is `<symbol>` defined?" | `mcp__tricorder__tricorder_detect` or `mcp__tricorder__tricorder_symbols` |
| Callers / callees of one symbol | `mcp__tricorder__tricorder_detail` |
| Graph traversal: callers/callees up to N hops, filtered | `mcp__tricorder__tricorder_query` — `callers('sym') depth=2 exclude=tests/**` |

Don't scan for a known symbol — go straight to `detect`/`symbols`. Scan only for structure.

## Workflow — escalation ladder (stop at the first rung that answers the question)

The point of tricorder is to NOT read every file. Climb the ladder; stop at the first rung that answers the question. Pulling a full file is the **last resort, not the default**.

1. **T0 map (auto-injected)** — the `[tricorder]` digest at turn 0 already gives you the repo skeleton: file paths + symbol names + line numbers. Often enough to know *which* file. **Don't re-scan** — the digest is current.
2. **Locate** — `mcp__tricorder__tricorder_detect {query}` (case-insensitive, token-cheap) or `mcp__tricorder__tricorder_symbols {query, file?, type?}` for a definition + signature + line. Returns the what/where without reading the file. One-call shortcut: `mcp__tricorder__tricorder_locate {query, max_tokens?}` runs detect → detail and returns the best match's body plus alternatives — use it when you already know you'll deep-dive the top hit.
2b. **Diff** — `mcp__tricorder__tricorder_diff {project_root}` answers "what changed since the last scan?" (added/modified/deleted + tags for changed files). Read-only.
3. **Graph query** — need callers/callees up to N hops? `mcp__tricorder__tricorder_query {query: "callers('sym') depth=2 exclude=tests/**"}` returns the exact subgraph in one call (nodes + edges), replacing 5+ round-trips. `tests_for('sym')` restricts to test files ("what tests cover this?").
4. **Deep-dive** — `mcp__tricorder__tricorder_detail {name, file, line}` returns the **full symbol body** + cross-file callers/callees. For most "how does X work" questions this is enough — you get the implementation, not just the signature, at a fraction of a full-file read.
5. **Escalate the map tier** — still missing context? `mcp__tricorder__tricorder_scan {project_root, tier: 1, context_lines: 3}` gives definitions + surrounding lines (~350 tokens/tag, ~25x T0). Use `output_format: "mermaid"` for a module dependency graph. Narrow with `chat_files`/`mentioned_files` to keep it small.
6. **Full file read — last resort** — `read_file` only when all of the above left genuine ambiguity (a bug spans half a file, you need a comment block far from any symbol, etc). Read the *specific line range* found in step 2/3, not the whole file blindly. A whole-file pull is a confession that the ladder failed.

**Token economics**: T0 ≈ 14 tokens/tag. T1 ≈ 350 tokens/tag. `detail` returns one symbol body (typically 50-400 tokens, capped by its 2048-token default budget on hot symbols). A full file read is thousands. Escalate deliberately.

### Required param

All MCP tools require `project_root` (absolute path) — they route against that root, so pass the real filesystem path.

## tricorder_scan parameters

- `project_root` (required), `token_limit` (default 8192), `tier`: `0` = definitions only (default) or `1` = + context lines
- `output_format`: `text` or `mermaid`; `chat_files`, `other_files`, `mentioned_files`, `mentioned_idents`
- `exclude_unranked`, `exclude_untagged`, `force_refresh`, `dry_run`, `max_files`
- `exclude_globs`: list of glob patterns (relative, POSIX) to drop from the auto-scan before ranking. Use for vendored/third-party subtrees, e.g. `["vendor/**"]`, `["third_party/**"]`. Ignored when `other_files` is explicitly provided.
- `pre_index` / `pre_index_max_files` (default 100) / `pre_index_include_parents` (default 0): when `other_files` is not given, narrow the scan to files containing a probe symbol (same fast path as the CLI `--pre-index` family). Use for huge repos (e.g. the Linux kernel) to avoid a full-tree walk on every call — the linux bench uses `pre_index="pick_next_task"` to scope to `kernel/sched/*`.

## tricorder_detect parameters

- `project_root` (required, absolute path), `query` (required — identifier to find, case-insensitive), `max_results` (default 10), `context_lines` (default 1), `include_definitions` (default true), `include_references` (default true).
- `pre_index` / `pre_index_max_files` (default 100) / `pre_index_include_parents` (default 0): scope the search to files containing a probe symbol instead of scanning the whole tree. Critical for huge repos — prevents a full-tree walk per query.

## CLI reference

```bash
tricorder . --map-tokens 2048                # map cwd
tricorder src/ --tier 1 --context-lines 3    # T1 with context
tricorder --chat-files main.py --other-files src/ --mermaid
tricorder --force-refresh .                  # bust stale tag cache
tricorder --exclude-globs vendor/** third_party/** .  # skip vendored code
tricorder --root . --map-tokens 2048           # no paths → auto-discover --root (--max-files, default 1000)
```

Tier tokens: T0 ≈ 14 tokens/tag (definitions), T1 ≈ 350 tokens/tag (with context).

## DB backend — where state lives

Scans populate a sqlite DB (tags/refs/meta tables) under the tricorder
workspace: `<workspace>/.tricorder/` (`db/`, `cache/`, `indexes/`, `output/`),
gitignored. `detect`/`symbols`/`detail`/`query` read that DB (PageRank-ranked);
`scan` builds or refreshes it. Tiers apply to `scan` output only — the DB
lookups have no tiers. Nothing is ever written into the scanned repo
(`utils.safe_write` raises unless the target resolves inside the cache root;
override the root via `TRICORDER_CACHE_HOME`).

- The DB is reused across runs — no rebuild when nothing changed.
  `force_refresh: true` (CLI `--force-refresh`) forces a rebuild.
- `--max-files` caps a CLI scan (default 1000; `--max-files 0` = unlimited).
  The MCP `tricorder_scan` `max_files` param instead defaults to 0 (unlimited) —
  set it explicitly on large repos. Truncation is logged server-side; verify
  coverage before trusting a map.
- `pre_index` narrows huge repos to files containing a probe symbol
  (rg fast path, ctags fallback) instead of walking the whole tree.

## Don't — discipline

- **Don't pull a full file before trying `detect` → `symbols` → `detail`.** The ladder exists because `detail` returns the body at a fraction of the cost. A whole-file read is the last rung.
- **Don't treat the digest as a full answer.** It's direction, not proof.
- **Don't open the whole repo first.** Use the map to narrow.
- **Don't re-scan when the digest already points at the right area.** It's current.
- **Don't guess file locations.** Query MCP.
- **Don't ask the user to run `/tricorder scan`** unless the map is stale (file changes not reflected).

## Pitfalls

- **Stale DB → empty/odd maps**: after installing new tree-sitter parsers or an upgrade, maps can look wrong from a cached parse. Run `--force-refresh` (MCP: `force_refresh: true`) to rebuild the DB.
- **State lives in the tricorder workspace** (`<workspace>/.tricorder/`), never in the scanned repo — don't ship or commit it, and never expect it inside the target project.
- `project_root` must be absolute; relative paths are not trusted.
- `tricorder_detect` is case-insensitive and token-cheap — prefer it over a full scan to find an identifier.
- **Detect/symbols auto-rescue**: when a query matches nothing, both tools deterministically retry orthographic variants (strips template args/parens/namespace, camel/snake/kebab/case forms) so decorated lookups like `PCM::AddToBuffer<128,128>` still resolve. Rescue hits are tagged `quality: "fuzzy"` — verify them against source before asserting behavior; `"exact"` hits matched the literal query.
- **Arg names are exact** — the tools use strict MCP names, so a wrong guess costs a rejected call before the schema comes back. The ones that bite: `tricorder_scan` takes `project_root` (not `files`/`path`), `tricorder_detect` takes `query` (not `identifier`), `tricorder_detail` takes `name`+`file`+`line` (not `symbol`). Coping them correctly up front skips the round-trip.
- **Function-scope isolation**: `get_symbol_detail` callers/callees must be scoped to the function body, not the whole file. The cross-file callees loop was missing the line-range guard, leaking sibling function refs. See `references/function-scope-isolation.md` for the bug pattern and fix.
- **Routing**: call each tool on its own — never batch multiple tools in one call. If a call is rejected, follow the rejection's own direction once instead of abandoning the tool (deferral varies: one setup routes via wrapper, another direct — the error tells you which).
- **Dead ends stay dead**: a 0-match detect/query, a `not found` detail, or a mangled `search_files` regex (backslash escapes aren't supported — use plain substrings) means move on with a different term on the FIRST failure. Never re-issue the same failing pattern.
- **Symbols dumps are the cost cliff**: an unbounded symbols listing (tens of KB) is the single biggest context bloat. Prefer a targeted `query` edge-trace or one `read_file`; call `symbols` at most once per investigation.
- **Metadata is direction, not proof**: never assert behavior from signatures/summaries alone — inspect the source lines before claiming what code does.

## Benchmark Efficacy

Proven numbers live in `references/efficacy.md` — read it when you need
savings figures or bench run instructions, not on every investigation.

## Developing / Maintaining Tricorder

Contributor notes (write-invariant, TC audit, verify recipes) live in
`references/contributing.md` — read it when editing tricorder itself.
