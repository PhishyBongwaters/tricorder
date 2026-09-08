# Tricorder README — Claims Inventory

A flat list of every factual claim made in README.md, grouped by section,
for validation against source code. Each claim maps to a checkable statement;
validation status starts as `pending` and is updated as checks run.

---

## 1. Executive Summary

- [pending] Tricorder produces a 40K-token map from 50M-token Linux kernel with 99.9% token savings
- [pending] Map points to `kernel/sched/fair.c:pick_next_task`
- [pending] Map generates in ~1.1s

## 2. Why Tricorder Matters

- [pending] Traditional approach reads every file (hours)
- [pending] Tricorder approach maps intelligently (seconds)
- [pending] 15/15 benchmarks pass across C++, Rust, TypeScript, Go, Linux kernel

## 3. Three Integrated Interfaces

- [pending] CLI: `tricorder .` maps current dir
- [pending] MCP: `tricorder-mcp` runs over STDIO
- [pending] Hermes/DSH: plugins + turn-0 digest auto-inject at session start

## 4. Smart Escalation Ladder

- [pending] T0 MAP: ~14 tokens/tag
- [pending] DETECT: ~1-2 tokens/tag
- [pending] DETAIL: ~50-400 tokens
- [pending] T1 SCAN: ~350 tokens/tag
- [pending] FULL FILE: last resort, reads entire file

## 5. Quick Start

- [pending] `python -m venv .venv && .venv/Scripts/pip install -r requirements.txt` works
- [pending] `tricorder .` maps current directory
- [pending] `tricorder . --mermaid --top 10` produces dependency graph

## 6. Core Features

- [pending] Uses tree-sitter + PageRank
- [pending] Binary search fits map to budget (~1.5% of full repo)
- [pending] `--pre-index SYMBOL` narrows huge trees in ~1s (rg-first, no full walk)
- [pending] Graph query DSL: `callers('auth') depth=2 exclude=tests/**`
- [pending] Mermaid graphs — dependency flowcharts with chat files highlighted
- [pending] Cross-file call graph — import-resolved callers/callees
- [pending] Caching — content-aware invalidation, outside repo (TC-003)
- [pending] 28 languages total
- [pending] 11 languages with signatures + return types

## 7. CLI Usage > Basic Mapping

- [pending] `tricorder .` maps current directory
- [pending] `tricorder src/ --map-tokens 2048` works with specific dir + token limit
- [pending] `tricorder file1.py file2.py` maps specific files
- [pending] `tricorder --chat-files main.py --other-files src/` works with prioritized file sets

## 8. CLI Usage > File Priority Order

- [pending] 1. `--chat-files` — highest priority
- [pending] 2. `--mentioned-files` — high priority
- [pending] 3. `--other-files` — lowest priority

## 9. CLI Usage > Advanced Options

- [pending] `tricorder . --verbose` works
- [pending] `tricorder . --force-refresh` busts cache
- [pending] `tricorder . --exclude-unranked` drops zero-score files
- [pending] `tricorder . --exclude-untagged` drops files with no symbols
- [pending] `tricorder . --quiet` works
- [pending] `tricorder . --dry-run --map-tokens 2048` works
- [pending] `tricorder . --max-files 5000` raises auto-discovery cap (default 1000)
- [pending] `tricorder . --exclude-globs vendor/** third_party/**` works
- [pending] `tricorder . --top 10` selects top N ranked files
- [pending] `tricorder . --mermaid --mermaid-top 30` produces Mermaid flowchart
- [pending] `tricorder . --signature-only` gives content signature for cache debugging
- [pending] `tricorder . --full` emits full map regardless of token budget (newly added)

## 10. CLI Usage > Output Tiers

- [pending] T0 (default): definition lines only — ~14 tokens/tag
- [pending] T1: definitions + N lines context — verify relevance without loading full files
- [pending] `tricorder . --tier 0` works
- [pending] `tricorder . --tier 1 --context-lines 3` works
- [pending] `tricorder . --tier 1 --context-lines 5 --map-tokens 4096` works

## 11. CLI Usage > Optimal Agent Workflow

- [pending] Direct access (0 tokens): path known → read directly; symbol known → tricorder_detect/grep
- [pending] Architecture overview (~1K-3K tokens): `tricorder . --mermaid`
- [pending] Subsystem symbols (~1K-2K tokens): `--tier 0` scoped to `src/sub/`
- [pending] Targeted reading (~100-500 tokens): `read_file` with line numbers from map
- [pending] Huge-repo drill-in: `--pre-index SYMBOL` for giant trees

## 12. CLI Usage > Pre-Index Probe

- [pending] `tricorder D:/Projects/linux --pre-index "pick_next_task" --pre-index-max-files 20 --map-tokens 2048` works
- [pending] rg-first: `rg -l -w SYMBOL` with multi-language globs — no index, no full-tree walk
- [pending] 6-file `kernel/sched/` narrow on Linux kernel yields full map in ~1.1s
- [pending] ctags fallback only if rg finds nothing
- [pending] `--pre-index-max-files N` default 100
- [pending] `--pre-index-include-parents N` default 0
- [pending] `pick_next_task` (~6 matches) lands on `kernel/sched/`; `schedule` (thousands) caps out
- [pending] Same `pre_index`/`pre_index_max_files`/`pre_index_include_parents` args available on MCP `tricorder_scan` and plugin

## 13. MCP Server

- [pending] Tricorder runs as MCP server over STDIO
- [pending] Hermes integration: register under `mcp_servers:` in config
- [pending] Other clients: Cline/Roo via `cline_mcp_settings.json`
- [pending] Direct run: `python tricorder_server.py`

## 14. MCP Tools

- [pending] `tricorder_scan` generates repo map; `output_format`: `text` or `mermaid`
- [pending] `tricorder_scan` `tier`: `0` or `1`
- [pending] `tricorder_scan` params: `token_limit`, `chat_files`, `other_files`, `mentioned_files/idents`, `exclude_unranked`, `exclude_untagged`, `force_refresh`, `max_context_window`, `output_file`, `dry_run`, `exclude_globs`, `pre_index`/`pre_index_max_files`/`pre_index_include_parents`, `full`
- [pending] `tricorder_scan` returns `token_estimate`, `full_repo_estimate`, `savings_pct`, `tier_hint`
- [pending] `tricorder_detect` searches identifiers by name; case-insensitive
- [pending] `tricorder_detect` params: `query`, `max_results`, `context_lines`, `include_definitions`, `include_references`, `pre_index`/`pre_index_max_files`/`pre_index_include_parents`
- [pending] `tricorder_symbols` structured symbol query with type + file filters
- [pending] `tricorder_symbols` returns name, type, file, line range, signature, docstring, language, ts-kind
- [pending] `tricorder_symbols` params: `query`, `type`, `file`, `limit` (default 50, cap 200)
- [pending] `tricorder_detail` deep-dive: body, callers, callees
- [pending] `tricorder_detail` params: `name`, `file`, `line`
- [pending] `tricorder_query` graph traversal DSL
- [pending] `tricorder_query` DSL: `callers('sym') depth=2 exclude=tests/** | callees('other') type=class`
- [pending] `tricorder_query` returns `{nodes, edges, token_estimate, savings_pct}`
- [pending] Example `tricorder_scan` (mermaid) call shown
- [pending] Returns `{"map": "<mermaid flowchart>", "report": {...}}`
- [pending] Chat files highlighted in pink

## 15. Hermes Lifecycle Plugin

- [pending] Plugin at `plugins/tricorder/` installs to `~/.hermes/plugins/tricorder/`
- [pending] Plugin wires `on_session_start` + `pre_llm_call` to inject turn-0 probe digest
- [pending] Turn-0 digest: language tally + file count + line estimate + MCP tool pointer
- [pending] Never builds full map on turn 0
- [pending] Registers `/tricorder` slash commands

## 16. Slash Commands

- [pending] `/tricorder root <path>` sets active project (persists)
- [pending] `/tricorder root <path>` checks cache: valid → "cache ready"; stale/missing → auto-rebuild
- [pending] `/tricorder scan [path]` force-rebuilds repo map (default: active project), ignores signature
- [pending] `/tricorder status` shows active project + cache state (valid/stale/missing, age) + all cached projects

## 17. Plugin Config

- [pending] Under `plugins.entries.tricorder.*` in config.yaml
- [pending] `active_project` is required — string
- [pending] `exclude_globs` is list — glob patterns (POSIX, relative to active_project)
- [pending] `hermes config set plugins.entries.tricorder.active_project D:/Projects/projectm` works
- [pending] `hermes config set plugins.entries.tricorder.exclude_globs '["vendor/**","third_party/**"]' --force` works
- [pending] Cache validity: Stat-based content signature (not TTL)
- [pending] CLI `--signature-only` computes sha256 over `{path}:{size}:{mtime}` per source file
- [pending] Plugin shells to CLI for signature, compares to stored `project_sig`
- [pending] Changing `exclude_globs` changes file set → signature changes → rebuild triggered

## 18. Installation

- [pending] `hermes plugins install "http://127.0.0.1:3001/projects/tricorder.git#plugins/tricorder" --force --enable` works
- [pending] `hermes config set plugins.entries.tricorder.active_project D:/Projects/<repo>` works

## 19. DSH Integration

- [pending] Turn-0 probe-digest injector: `plugins/dsh-tricorder-inject/` (vendored Cordis plugin)
- [pending] Runs `tricorder --root <cwd> --probe-digest`
- [pending] MCP tools + skill at `skills/tricorder-dsh/SKILL.md`
- [pending] MCP server registered as `tricorder` via `dsh-mcp-client`
- [pending] `pip install -e "D:/Projects/tricorder"` works
- [pending] `mkdir -p ~/.dsh/skills/tricorder` works
- [pending] `cp "D:/Projects/tricorder/skills/tricorder-dsh/SKILL.md" ~/.dsh/skills/tricorder/SKILL.md` works
- [pending] `cordis.patch.yml` example shown works

## 20. Benchmarks

- [pending] Efficacy measured with `bench/bench_validity.py` (CLI) and `bench/bench_validity_mcp.py` (MCP)
- [pending] Each task poses a realistic agent question
- [pending] `ground_truth` identifiers must appear in the map for a PASS
- [pending] projectm: 2/2 bench_validity.py, 2048 map tokens / 642,428 full / 99.7% savings
- [pending] projectm: 2/2 bench_validity_mcp.py, 221/1,358 map tokens / 642,428 full / 100.0%/99.8% savings
- [pending] vaultwarden: 2/2 bench_validity.py, 32,563 map tokens / 755,518 full / 95.7% savings
- [pending] vaultwarden: 2/2 bench_validity_mcp.py, 1,173/2,695 map tokens / 755,518 full / 99.8%/99.6% savings
- [pending] linux: 1/1 bench_validity.py, 39,936 map tokens / 50,352,437 full / 99.9% savings
- [pending] linux: 1/1 bench_validity_mcp.py, 5,500 map tokens / 50,352,437 full / 100.0% (pre-indexed)
- [pending] bitburner: 1/1 bench_validity.py, 65,024 map tokens / 1,504,232 full / 95.7% savings
- [pending] bitburner: 1/1 bench_validity_mcp.py, 205 map tokens / 1,504,232 full / 100.0% savings
- [pending] librechat: 1/1 bench_validity.py, 65,024 map tokens / 6,316,980 full / 99.0% savings
- [pending] librechat: 1/1 bench_validity_mcp.py, 1,560 map tokens / 6,316,980 full / 100.0% savings
- [pending] elixir: 1/1 bench_validity.py, 4,096 map tokens / 3,060,510 full / 99.9% savings
- [pending] elixir: 1/1 bench_validity_mcp.py, 6,911 map tokens / 3,060,510 full / 99.8% savings
- [pending] otp: 1/1 bench_validity.py, 102 map tokens / 46,463,905 full / 100.0% savings
- [pending] otp: 1/1 bench_validity_mcp.py, 202 map tokens / 46,463,905 full / 100.0% savings
- [pending] go: 1/1 bench_validity.py, 307 map tokens / 36,501,836 full / 100.0% savings
- [pending] go: 1/1 bench_validity_mcp.py, 19,587 map tokens / 36,501,836 full / 99.9% savings
- [pending] kotlin: 1/1 bench_validity.py, 64,204 map tokens / 13,984,544 full / 99.5% savings
- [pending] kotlin: 1/1 bench_validity_mcp.py, 8,810 map tokens / 13,984,544 full / 99.9% savings
- [pending] swift: 1/1 bench_validity.py, 64,409 map tokens / 38,017,250 full / 99.8% savings
- [pending] swift: 1/1 bench_validity_mcp.py, 5,793 map tokens / 38,017,250 full / 100.0% savings
- [pending] rails: 1/1 bench_validity.py, 64,819 map tokens / 5,445,557 full / 98.8% savings
- [pending] rails: 1/1 bench_validity_mcp.py, 6,601 map tokens / 5,445,557 full / 99.9% savings
- [pending] framework: 1/1 bench_validity.py, 65,024 map tokens / 4,218,620 full / 98.5% savings
- [pending] framework: 1/1 bench_validity_mcp.py, 5,583 map tokens / 4,218,620 full / 99.9% savings
- [pending] kong: 1/1 bench_validity.py, 53,145 map tokens / 3,440,558 full / 98.5% savings
- [pending] kong: 1/1 bench_validity_mcp.py, 97 map tokens / 3,440,558 full / 100.0% savings
- [pending] spring-boot: 1/1 bench_validity.py, 65,024 map tokens / 487,802 full / 86.7% savings
- [pending] spring-boot: 1/1 bench_validity_mcp.py, 448 map tokens / 487,802 full / 99.9% savings
- [pending] vue: 1/1 bench_validity.py, 1,433 map tokens / 549,971 full / 99.7% savings
- [pending] vue: 1/1 bench_validity_mcp.py, 5,738 map tokens / 549,971 full / 99.0% savings
- [pending] RESULT: ALL TASKS PASS (15 repos × 2 surfaces)
- [pending] projectm (~5,800 files, ~1.1M lines, C++): ~100% token savings
- [pending] projectm map covers `PCM::AddToBuffer`, `Loudness`, `CurrentRelative`, `AverageRelative`
- [pending] vaultwarden (~200 Rust files): ~96–99.8% token savings
- [pending] vaultwarden map covers `generate_invite`, `delete_user`, `admin_page`, `hash_password`, `verify_password_hash`, `routes`, `catchers`
- [pending] linux: With `--pre-index pick_next_task` map narrows to `kernel/sched/*` (~6 files) in ~1.1s
- [pending] linux map covers `pick_next_task`, `schedule`, `update_curr` at 99.9% savings
- [pending] Use a *specific* probe symbol (general `schedule` fails, specific `pick_next_task` works)
- [pending] MCP token shape differs from CLI: `bench_validity_mcp.py` exercises `tricorder_detect` (per-file definition records), not serialized map
- [pending] MCP tokens scale with result count per identifier
- [pending] projectm MCP tokens smaller than CLI map (1358 vs 2048)
- [pending] vaultwarden MCP tokens grow to ~2695
- [pending] Savings measured against same full-repo estimate in both suites
- [pending] MCP `tricorder_detect` supports `pre_index` (mirrors CLI `--pre-index`)
- [pending] linux MCP slot uses `pre_index="pick_next_task"` to narrow to `kernel/sched/*`
- [pending] linux MCP runtime dropped from ~168s to ~64s with pre-index
- [pending] linux MCP no longer cold-cache-flaky with pre-index: verified 3x consecutive PASS

## 21. Running Tests

- [pending] Tests: `tests/test_cli_autodiscovery.py tests/test_mcp.py tests/test_utils.py tests/test_regression_phase1.py`
- [pending] Full suite: `python -m pytest tests/ -v`
- [pending] Tests insert `.` into `sys.path`; pytest must be run from repo root

## 22. Reproduce Benchmarks

- [pending] `python bench/bench_validity.py` (all 15 repos, CLI)
- [pending] `python bench/bench_validity_mcp.py` (MCP surface)
- [pending] `python bench/bench_validity.py linux` (linux fast-path only)
- [pending] `python bench/bench_validity.py bitburner` (single repo by name)
- [pending] `python bench/bench_validity.py --root /path/to/your/repos` (custom checkouts)
- [pending] `rg` must be on PATH for `--pre-index` fast path
- [pending] Task definitions live in `bench/bench_validity*.py`
- [pending] No CI bench machinery — run locally; numbers reproducible on same public repos
- [pending] Repos: projectm at `D:\Projects\projectm`; rest under `D:\Projects\Tricorder-Testing-Repos/<folder>`
- [pending] bitburner folder is `bitburner-src`

## 23. Security Model

- [pending] TC-005: Every MCP response stamped `source: scanned_repository`, `trust: untrusted_repository_content`
- [pending] TC-001: Raw map wrapped in `BEGIN/END UNTRUSTED REPOSITORY CONTEXT` markers
- [pending] TC-006: `chat_files` / `detail` file params rejected if they resolve outside `project_root`
- [pending] TC-007: MCP `max_files` clamped to 10,000 server-side; discovery early-stops at 20,000
- [pending] TC-008: `output_file`/`--output` writes contained: server output to `get_cache_root()/.tricorder/output/<basename>`
- [pending] TC-008: Honors `TRICORDER_CACHE_HOME`
- [pending] TC-008: `--output` is the sole sanctioned user-chosen path outside cache root
- [pending] TC-008: `--output` still fails gracefully (honest error + stdout fallback) if path is unwritable
- [pending] TC-008: All in-process writes route through `utils.safe_write()`, which raises `ValueError` on any target escaping cache root
- [pending] TC-002: Global budget — max 20k files, 500 MB, depth 25, 300s, 1 MB/file
- [pending] TC-002: Resource envelope limits → partial result + `scan_warning`
- [pending] TC-002: Tunable via `TRICORDER_MAX_*` env vars
- [pending] TC-003: Tags cache lives outside the repo
- [pending] TC-004: Each tree-sitter parse has 5s hard timeout (`TRICORDER_PARSER_TIMEOUT_S`)
- [pending] TC-004: Parser timeout skips hang, doesn't stall
- [pending] TC-009: `requirements.txt` fully pinned
- [pending] TC-009: `scripts/depscan.py` emits pinned inventory + `pip-audit`
- [pending] TC-010: `tests/security/` holds adversarial fixtures
- [pending] TC-010: Adversarial fixtures assert no crash/hang

## 24. Environment Overrides

- [pending] `TRICORDER_MAX_SCAN_FILES=20000`
- [pending] `TRICORDER_MAX_TOTAL_BYTES=524288000`
- [pending] `TRICORDER_MAX_SCAN_DEPTH=25`
- [pending] `TRICORDER_MAX_SCAN_TIME_S=300`
- [pending] `TRICORDER_MAX_SOURCE_FILE_SIZE=1048576`
- [pending] `TRICORDER_PARSER_TIMEOUT_S=5`
- [pending] `TRICORDER_CACHE_HOME=<tricorder workspace>/.tricorder` (default; controls cache + output root)

## 25. Supported Languages

- [pending] Signature extraction + return types for: Python, JavaScript, TypeScript, C, C++, Java, Go, Rust, Swift, C#, Ruby (11 grammars)
- [pending] Enforced by `tests/test_language_matrix.py` (`test_claimed_languages_extract_defined_signature`)
- [pending] Wider parse support for 28 total languages via `tree-sitter-language-pack` (29 grammars listed)
- [pending] `tree-sitter-languages` (22 grammars) adds: kotlin, php, ql, scala, typescript
- [pending] Union = 28 distinct languages
- [pending] Canonical list in `utils.py` `EXTENSIONS`
- [pending] `.h` files mapped to `cpp` (cpp grammar is strict superset of C)
- [pending] Language registry (ctags_probe.py): Single source of truth for 24 languages
- [pending] Shared by ctags pre-index probe and tree-sitter extraction
- [pending] `tricorder_detect` search modes: `exact` (whole word), `substring` (default), `regex` (Python regex)
- [pending] Case-insensitive for exact/substring modes
- [pending] Adding a new language (e.g. Zig) is one registry entry

## 26. Caching

- [pending] Cache location: `<tricorder workspace>/.tricorder/cache/<sha1(repo_path|version|config)>/`
- [pending] Cache is outside the repository (TC-003)
- [pending] Repo never controls cache state
- [pending] Default cache root is tricorder workspace `.tricorder` dir (always writable)
- [pending] Override with `TRICORDER_CACHE_HOME`
- [pending] Server map output lands under cache root (`<cache root>/output`)
- [pending] Server output contained by same `safe_write()` guard
- [pending] `--output` is only write that may target user-chosen path outside cache root
- [pending] `--signature-only` prints 16-char content signature

## 27. Lineage & Attribution

- [pending] Gen 1 — Aider `RepoMap` (Paul Gauthier): tree-sitter + PageRank
- [pending] Gen 2 — RepoMapper (Paul Davis / pdavis68): standalone CLI + MCP server
- [pending] Gen 3 — tricorder: fork — 8 bug fixes, 123 tests, 10-language signature extraction, cross-file call graph, ctags/rg pre-index probe, Windows compatibility, full rebrand
- [pending] MIT Licensed
- [pending] Based on the RepoMap design from the Aider project

## 28. License

- [pending] MIT
- [pending] Based on the RepoMap design from the Aider project

---

## Validation Log

Track progress here as claims are verified:

```
[date] [claim-section] [status: pass|fail|partial|pending] [notes]
```
