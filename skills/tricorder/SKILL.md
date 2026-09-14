---
name: codebase-tricorder
description: Use tricorder to map a codebase (symbols, call graphs, signatures) without reading every file. Highest-value when exploring an unfamiliar repo, locating a definition, or summarizing structure.
---

# Tricorder

Use tricorder when you need `symbols`, `signatures`, `callers/callees`, or a compact **map** of a codebase without reading every file. It scans with tree-sitter, ranks by PageRank, and returns only the important definitions — typically **~1.5% of full-repo token cost**.

It is surfaced two ways:

- **Native MCP tools** (primary): when tricorder is registered as an MCP server, its tools appear as `mcp__tricorder__tricorder_scan`, `mcp__tricorder__tricorder_detect`, `mcp__tricorder__tricorder_symbols`, `mcp__tricorder__tricorder_detail`, `mcp__tricorder__tricorder_query`.
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
2. **Locate** — `mcp__tricorder__tricorder_detect {query}` (case-insensitive, token-cheap) or `mcp__tricorder__tricorder_symbols {query, file?, type?}` for a definition + signature + line. Returns the what/where without reading the file.
3. **Graph query** — need callers/callees up to N hops? `mcp__tricorder__tricorder_query {query: "callers('sym') depth=2 exclude=tests/**"}` returns the exact subgraph in one call (nodes + edges), replacing 5+ round-trips.
4. **Deep-dive** — `mcp__tricorder__tricorder_detail {name, file, line}` returns the **full symbol body** + cross-file callers/callees. For most "how does X work" questions this is enough — you get the implementation, not just the signature, at a fraction of a full-file read.
5. **Escalate the map tier** — still missing context? `mcp__tricorder__tricorder_scan {project_root, tier: 1, context_lines: 3}` gives definitions + surrounding lines (~350 tokens/tag, ~25x T0). Use `output_format: "mermaid"` for a module dependency graph. Narrow with `chat_files`/`mentioned_files` to keep it small.
6. **Full file read — last resort** — `read_file` only when all of the above left genuine ambiguity (a bug spans half a file, you need a comment block far from any symbol, etc). Read the *specific line range* found in step 2/3, not the whole file blindly. A whole-file pull is a confession that the ladder failed.

**Token economics**: T0 ≈ 14 tokens/tag. T1 ≈ 350 tokens/tag. `detail` returns one symbol body (typically 50-400 tokens). A full file read is thousands. Escalate deliberately.

### Required param

All MCP tools require `project_root` (absolute path) — they route against that root, so pass the real filesystem path.

## tricorder_scan parameters

- `project_root` (required), `token_limit` (default 8192), `tier`: `0` = definitions only (default) or `1` = + context lines
- `output_format`: `text` or `mermaid`; `chat_files`, `other_files`, `mentioned_files`, `mentioned_idents`
- `exclude_unranked`, `exclude_untagged`, `force_refresh`, `dry_run`, `max_files`
- `exclude_globs`: list of glob patterns (relative, POSIX) to drop from the auto-scan before ranking. Use for vendored/third-party subtrees, e.g. `["vendor/**"]`, `["third_party/**"]`. Ignored when `other_files` is explicitly provided.
- `pre_index` / `pre_index_max_files` (default 100) / `pre_index_include_parents` (default 0): when `other_files` is not given, narrow the scan to files containing a probe symbol (same fast path as the CLI `--pre-index` family). Use for huge repos (e.g. the Linux kernel) to avoid a full-tree walk on every call — the linux bench uses `pre_index="pick_next_task"` to scope to `kernel/sched/*`.

## tricorder_detect parameters

- `project_root` (required, absolute path), `query` (required — identifier to find, case-insensitive), `max_results` (default 50), `context_lines` (default 2), `include_definitions` (default true), `include_references` (default true).
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
- `--max-files` caps a scan (default 1000, silently truncates past it with
  only a warning line); `--max-files 0` = unlimited. Verify coverage before
  trusting a map.
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

## Benchmark Efficacy

Proven across 2 real repos with 8 realistic agent tasks using two benchmark suites:

| Repo | Tasks | Suite | Map Tokens | Full Repo | Savings |
|------|-------|-------|------------|-----------|---------|
| projectm | 2/2 | bench_validity.py | 2,048 | 642,428 | 99.7% |
| projectm | 2/2 | bench_validity_mcp.py | 2,048 | 642,428 | 99.9% (MCP) |
| vaultwarden | 2/2 | bench_validity.py | 32,563 | 755,518 | 95.7% |
| vaultwarden | 2/2 | bench_validity_mcp.py | 32,563 | 755,518 | 99.6% (MCP) |

**RESULT: ALL TASKS PASS** — both benches confirm the tricorder T0 map (and MCP tools) steer agents to correct code without reading the full repo.

- **projectm** (~5,800 files, ~1.126K lines): ~100% token savings; 2K-token map covers all required identifiers (PCM::AddToBuffer, Loudness, CurrentRelative, AverageRelative)
- **vaultwarden** (~200 Rust files): ~96-99.8% token savings; 33K-token map covers all required identifiers (generate_invite, delete_user, admin_page, hash_password, verify_password_hash, routes, catchers)

*T0 maps and MCP tools (detect/symbols) provide massive token savings while retaining full task coverage. Both CLI and MCP surfaces are effective.*

### How to Run the Benches

```bash
# From d:/projects/tricorder/bench/
python bench_validity.py           # all repos
python bench_validity.py projectm  # projectm only
python bench_validity_mcp.py       # all repos
python bench_validity_mcp.py vaultwarden  # vaultwarden only
```

### Bench Results Summary

| Repo | Token Savings | Task Coverage |
|------|--------------|---------------|
| projectm | 99.7% (CLI) / 99.9% (MCP) | 2/2 tasks PASS |
| vaultwarden | 95.7% (CLI) / 99.6% (MCP) | 2/2 tasks PASS |

Both bench suites are self-contained, idempotent, and produce a table+readme-ready report on each run. Outputs `BENCHMARK_RESULTS.md` and updates `README.md` with a `Tricorder Efficacy` section.

## Developing / Maintaining Tricorder (contributor notes)

When editing the tricorder repo itself (not just calling it), the load-bearing invariants and recipes below hold. Full detail in `references/tricorder_dev_notes.md`.

### Write-invariant — never write into a scanned repo
Every in-process write routes through `utils.safe_write(path, text, *, allow_escape=False)`. Default: target must resolve inside `get_cache_root()` (== `<tricorder workspace>/.tricorder`, overridable via `TRICORDER_CACHE_HOME`) or it raises `ValueError` **loud** (not swallowed). `--output` is the only sanctioned escape (`allow_escape=True`); it still wraps the write in `except OSError` + stdout fallback so the map is never lost. I/O errors raise `OSError` so best-effort caches swallow only disk failures. Wired sites: `utils.py` budget cache, `ctags_probe.py` tags meta, `tricorder_server.py` output, `tricorder.py --output`. The plugin (`plugins/tricorder/__init__.py`) is intentionally out-of-process (shells to CLI in its own venv) and is NOT reached by `safe_write` — by design.

### TC-threat-model audit (cheap coverage check after any change)
Tickets TC-001..010 encode the security model. Grep the tests dir for `TC-0` (`rg "TC-0[0-9]" tests/ -n`) to confirm no ticket regressed to zero coverage. Last full audit: TC-001..008 + TC-010 covered; TC-009 (dep pinning) was the last gap → `tests/test_tc009_dep_pinning.py` asserts every `requirements.txt` line is `==`-pinned. Re-run the grep whenever you add/remove a behavior.

### Verify recipes (run from repo root — tests insert `.` into sys.path)
- Full suite: `python -m pytest tests/ -v` (baseline 185 passed, 19 subtests).
- `--output` escape hatch on native Windows `python.exe`: use a real Windows absolute path (`C:/tmp/check.json`). Native python does NOT translate MSYS `/tmp` — it becomes `D:\tmp\...` relative to cwd. Expect exit 0 + file written.
- Unwritable cache root: `TRICORDER_CACHE_HOME=/tmp/nw/blocker/.tricorder python tricorder.py scan .` → must still emit a map (exit 0), not crash.
- README keeps a "Running Tests (Agent Instructions)" section; keep it in sync when adding tests.
- Commit/push: Gitea `hermes-agent` identity, token inline in origin URL; push origin then github. Never use `~/.gitea_pat` (see gitea-workflow skill).