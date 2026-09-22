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
- [pending] DETAIL: ~50-400 tokens typical (≤2048 default budget)
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
- [pending] 34 languages total
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
- [pending] `tricorder . --max-files 5000` raises auto-discovery cap (default 0 = no cap)
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
- [verified 2026-09-20] `tricorder_scan` params match `tricorder_server.py` exactly (21 params): `project_root`, `chat_files`, `other_files`, `token_limit`, `exclude_unranked`, `force_refresh`, `mentioned_files`, `mentioned_idents`, `verbose`, `max_context_window`, `tier`, `context_lines`, `output_format`, `max_files`, `output_file`, `dry_run`, `exclude_globs`, `pre_index`, `pre_index_max_files`, `pre_index_include_parents`, `full` (no `exclude_untagged`)
- [pending] `tricorder_scan` returns `token_estimate`, `full_repo_estimate`, `savings_pct`, `tier_hint`
- [pending] `tricorder_detect` searches identifiers by name; case-insensitive
- [pending] `tricorder_detect` params: `query`, `max_results`, `context_lines`, `include_definitions`, `include_references`, `pre_index`/`pre_index_max_files`/`pre_index_include_parents`
- [pending] `tricorder_symbols` structured symbol query with type + file filters
- [pending] `tricorder_symbols` returns name, type, file, line range, signature, docstring, language, ts-kind
- [pending] `tricorder_symbols` params: `query`, `type`, `file`, `limit` (default 10, cap 200)
- [pending] `tricorder_detail` deep-dive: body, callers, callees
- [verified 2026-09-20] `tricorder_detail` params match `tricorder_server.py` exactly: `project_root`, `file`, `name`, `line`, `max_tokens`
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
- [pending] MCP tools + skill at `skills/tricorder/SKILL.md`
- [pending] MCP server registered as `tricorder` via `dsh-mcp-client`
- [pending] `pip install -e "D:/Projects/tricorder"` works
- [pending] `mkdir -p ~/.dsh/skills/tricorder` works
- [pending] `cp "D:/Projects/tricorder/skills/tricorder/SKILL.md" ~/.dsh/skills/tricorder/SKILL.md` works
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
- [pending] TC-007: MCP `max_files` clamped to 10,000 server-side; discovery early-stops at `TRICORDER_MAX_SCAN_FILES` only when set (0 = unlimited by default)
- [pending] TC-008: `output_file`/`--output` writes contained: server output to `get_cache_root()/.tricorder/output/<basename>`
- [pending] TC-008: Honors `TRICORDER_CACHE_HOME`
- [pending] TC-008: `--output` is the sole sanctioned user-chosen path outside cache root
- [pending] TC-008: `--output` still fails gracefully (honest error + stdout fallback) if path is unwritable
- [pending] TC-008: All in-process writes route through `utils.safe_write()`, which raises `ValueError` on any target escaping cache root
- [verified 2026-09-20] TC-002: Resource envelope — depth 25, 1MB/file bounded by default; file count, total bytes, scan time unlimited (0) by default, settable via `TRICORDER_MAX_SCAN_FILES` / `TRICORDER_MAX_TOTAL_BYTES` / `TRICORDER_MAX_SCAN_TIME_S`. Docs corrected 2026-09-20 (previously claimed enforced 20k/500MB/300s defaults).
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

- [pending] `TRICORDER_MAX_SCAN_FILES=0` (0 = unlimited; the former 20000 default was relaxed when `--full` was added)
- [pending] `TRICORDER_MAX_TOTAL_BYTES=0` (0 = unlimited; the former 524288000 default was relaxed when `--full` was added)
- [pending] `TRICORDER_MAX_SCAN_DEPTH=25`
- [pending] `TRICORDER_MAX_SCAN_TIME_S=0.0` (0 = unlimited; the former 300 default was relaxed when `--full` was added)
- [pending] `TRICORDER_MAX_SOURCE_FILE_SIZE=1048576`
- [pending] `TRICORDER_PARSER_TIMEOUT_S=5`
- [pending] `TRICORDER_CACHE_HOME=<tricorder workspace>/.tricorder` (default; controls cache + output root)

## 25. Supported Languages

- [pending] Signature extraction + return types for: Python, JavaScript, TypeScript, C, C++, Java, Go, Rust, Swift, C#, Ruby (11 grammars)
- [pending] Enforced by `tests/test_language_matrix.py` (`test_claimed_languages_extract_defined_signature`)
- [verified 2026-09-20] 34 languages with tree-sitter query files under `queries/` (verified: 34 of 38 `CODE_EXTENSIONS` languages have a `*-tags.scm`; css, html, objc, systemverilog map extensions but have no query file)
- [pending] Canonical extension table in `utils.py` `CODE_EXTENSIONS` (53 extensions → 38 languages)
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
- [pending] Gen 3 — tricorder: fork — 301+ tests, 11-language signature extraction, cross-file call graph, ctags/rg pre-index probe, Windows compatibility, DB-backed ranking with extractor versioning
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

[2026-09-20] [§14 MCP Tools] [pass] All 7 tool signatures in `tricorder_server.py` match `docs/mcp-reference.md` param tables exactly (scan 21, detect 10, symbols 5, diff 1, detail 5, locate 4, query 3). Claims §14 updated: scan has no `exclude_untagged`; detail has `max_tokens`.
[2026-09-20] [§6/§9 CLI] [pass] All 39 `--help` flags appear in `docs/cli-reference.md`; `--since` alias documented in README + cli-reference.
[2026-09-20] [§25 Languages] [pass] 34 languages have tree-sitter query files under `queries/` (CODE_EXTENSIONS maps 53 extensions → 38 languages; css/html/objc/systemverilog have no query file). 11 signature-extraction languages enforced by `tests/test_language_matrix.py`. Claims §25 updated (was stale: 28 languages, `utils.EXTENSIONS`).
[2026-09-20] [README counts] [pass] Badge + contributing + lineage all say 301, matching `pytest tests/ --ignore=tests/test_e2e_mcp.py` (301 passed, 3 skipped, 93 subtests).
[2026-09-20] [Prose audit] [pass-with-fixes] Deep audit of user-guide/SPEC/architecture/cli-reference/benchmarks found 8 issues, all fixed: (1) resource-envelope defaults were documented as enforced 20k/500MB/300s but code defaults are 0=unlimited since the --full feature commit (docs corrected; duplicate `_MAX_SCAN_DEPTH` line removed; stale comments in utils.py + tricorder_server.py fixed); (2) SPEC "MCP Tools (5)" → 7 with diff/locate sections added; (3) SPEC "199 tests" ×4 → 301; (4) SPEC "10-language" ×2 → 11; (6) turn-0 plugin described as probe-only, actually DB-first with probe fallback (user-guide + cli-reference + SPEC corrected); (7) `scan_warning` is MCP-only, CLI uses stderr; (8) >100MB tag files are skipped, not "treated as corrupt". (5) was a false positive: "34 languages with tree-sitter queries" is correct (css/html/objc/systemverilog are ext-mapped but "no-query").

[2026-09-20] [README counts] [pass-with-fixes] Badge + contributing + AGENTS.md updated 339→351 to match latest suite (351 passed, 1 skipped, 93 subtests). Lineage "301+ tests" → "351 tests". Supersedes the 2026-09-20 301-count entry.
[2026-09-20] [§25 Languages] [pass-with-fixes] Supersedes the 34-language/11-signature entry: `tests/test_language_matrix.py` now enforces 93 validated languages (11 full-signature + 82 definition-only); 95 query files across both `queries/` trees; 3 query-present-not-in-matrix (hcl, properties, udev); 13 grammar-but-no-query potentials measured from the installed pack (105 grammars). `docs/v2/06-languages.md` Potential section was wrong (claimed 51, listed validated languages as potential) and rewritten with measured values.

[2026-09-20] [Docs audit round 5] [pass-with-fixes] Fresh-eyes audit of root README + docs/v2/03/04/05/07 found 9 real issues, all fixed: (1) README "Measured: 15/15 benchmarks" contradicted docs/v2/README "no benchmark numbers claimed on this branch until re-measured" — now qualified as pre-db-map (Gen 2), re-measurement pending; (2) README kernel example cited `kernel/sched/fair.c` but benchmarks.md only says `kernel/sched/` — filename dropped; (3) README "DB-backed scanning (default)" — fresh repos scan in-memory until `--init` (tricorder.py:_effective_db_path docstring) — wording corrected; (4) 05-setup said rg required for --pre-index — actually degrades gracefully (ctags fallback, then full walk with warning) — corrected; (5) 05-setup "requirements.txt pins the same set for CI" — false (no mcp, fastmcp pin below pyproject floor) — softened to last-known-good; (6) 04-internals "Requires the rg binary on PATH" — removed; (7) 03-operations `.tricorder.tags.cache.v1/` — no such dir exists (cache.py:_cache_dir uses `<root>/cache/<sha1>`); corrected; (8) 07-language-expansion "ql/wast/wat (no ext mapping)" — all three have ext mappings and are matrix-green — dropped from unproven; (9) 07 "wgsl_bevy → wgsl (once written)" — wgsl query exists and is Tier A DONE — fixed. One reported issue was a false positive: 07's "systemverilog → verilog (no work)" is correct — detect_lang maps `.sv` → verilog and .sv files extract tags (verified empirically). 06-languages Potential section rewritten method-based after finding the pack lazily downloads grammars (count 13→17 during the audit).

[2026-09-20] [README counts] [pass-with-fixes] Badge + contributing + lineage + AGENTS.md updated 351→365 (3 skipped, env-dependent: ctags/rg absent in this environment; the old "(Windows-only)" parenthetical was wrong). Verified against full suite: 365 passed, 3 skipped, 93 subtests. Supersedes the 351-count entry.
[2026-09-20] [Round 8 code review] [pass-with-fixes] Fresh-eyes sweep found 5 verified issues, all fixed + regression-tested (tests/test_review_round8.py; 6/7 fail pre-fix): (1) `_canonical_db_for`/`_get_tricorder` @lru_cache hid canonical DBs created by `tricorder --init` after server start — lookup is now uncached, instance cache re-resolves the DB path per call and rebuilds on change (TC-011 warmth preserved); (2) `read_only_connect` interpolated raw paths into SQLite URIs, silently mistargeting DBs under `#`/`?` dirs — now `Path.as_uri()`; turn-0 plugin's two inline `mode=ro` opens got the same fix plus `immutable=1` (inline: the plugin never imports tricorder in-process); (3) `--db-path <directory>` on the scan path died with a raw sqlite3 traceback — clean `parser.error` now covers scan + diff; (4) stale test counts (this entry); (5) `--no-db` help claimed mutual exclusion with `--db-path` but the parser enforced nothing — real mutually-exclusive group added. Docs claims for `--diff` read-only verified to match code after rounds 6-7.

[2026-09-20] [README counts] [pass-with-fixes] ctags built from source (universal-ctags 6.2.1, ~/workspace/bin/ctags) — the 2 rg/ctags env skips now run and pass. Counts updated 365→367, skips 3→1 (the remaining skip is genuinely Windows-only: tests/test_mcp.py backslash normalization). Full suite: 367 passed, 1 skipped, 93 subtests. Supersedes the 365-count entry.
[2026-09-20] [README counts] [pass-with-fixes] Round 9 added 5 tests (tests/test_review_round9.py): MCP cache thread-safety, wipe/replace rebuild, locked-wipe error, plugin URI special chars. Counts updated 367→372, still 1 Windows-only skip. Full suite: 372 passed, 1 skipped, 93 subtests. Supersedes the 367-count entry.

[2026-09-20] [README counts] [pass-with-fixes] Round 10: 372→380 (8 new tests in tests/test_review_round10.py: WAL-checkpoint visibility, diff-after-incremental, LRU-eviction close, diff/scan handle close, KeyboardInterrupt exit 130, --db-coverage house-rule). Full suite: 380 passed, 1 skipped (Windows-only), 93 subtests. Supersedes the 372-count entry.
[2026-09-20] [README counts] [pass-with-fixes] Round 11: 380→383 (3 new tests in tests/test_review_round11.py: extractor-version staleness vs per-file tag disk cache and cross-ref disk bundle — both now keyed/fingerprinted with EXTRACTOR_VERSION). Also fixed an inverted Quick Start parenthetical: the --pre-index fast path is ripgrep-first with ctags as fallback, not the reverse. Full suite: 383 passed, 1 skipped (Windows-only), 93 subtests. Supersedes the 380-count entry.

[2026-09-20] [README counts] [pass-with-fixes] Round 12: 383→392 (9 new tests in tests/test_review_round12.py: plugin coverage house-rule, rescan empty-map fallback, single-tag binary-search fix, render-cache content fingerprint, delete-resume). Full suite: 392 passed, 1 skipped (Windows-only), 93 subtests. Supersedes the 383-count entry.

[2026-09-20] [README counts] [pass-with-fixes] Round 13: 392→393 (1 new test in tests/test_review_round13.py: --diff symlink phantom-added — diff_against_index now resolves symlinks before the rel computation, matching the scan path). Full suite: 393 passed, 1 skipped (Windows-only), 93 subtests. Supersedes the 392-count entry.

[2026-09-20] [README counts] [pass-with-fixes] Round 14: 393→398 (5 new tests in tests/test_review_round14.py: scan skips symlinks resolving outside the repo root — absolute host paths no longer enter the DB as rels; --diff ignores outside-root symlinks; symlink loops no longer crash the scan (defensive resolve_or_none in CLI/MCP/API paths); plugin build_map returns None on nonzero CLI exit instead of serving a stale map as fresh). Full suite: 398 passed, 1 skipped (Windows-only), 93 subtests. Supersedes the 393-count entry.

[2026-09-20] [README counts] [pass-with-fixes] Round 15: 398→404 (6 new tests in tests/test_review_round15.py: corrupt --db-path fails clean — DBStore raises ValueError("Not a SQLite database") via magic-header check plus DatabaseError conversion for truncated files; CLI scan/diff/--init surface the message with exit 1, no traceback; --diff no longer misreports a corrupt DB as "no index"; 0-byte DB files still initialize). Full suite: 404 passed, 1 skipped (Windows-only), 93 subtests. Supersedes the 398-count entry.

[2026-09-20] [README counts] [pass-with-fixes] Round 16: 404→407 (3 new tests in tests/test_review_round16.py: file_state mtime stored at nanosecond resolution (st.st_mtime_ns) via new utils.stat_fingerprint() — same-second same-size edits are now detected by the incremental rescan and --diff instead of serving stale tags forever; --signature-only and the render-cache fingerprint also moved to ns; old second-resolution DBs self-heal with one full re-parse on first scan after upgrade). Full suite: 409 passed, 1 skipped (Windows-only), 93 subtests. Supersedes the 404-count entry.

[2026-09-20] [README counts] [pass-with-fixes] Static audit round: 407→409 (2 new tests in tests/test_static_audit.py: render._cached_tree_context now keys on st_mtime_ns instead of float st_mtime; parser.get_tags_raw's ImportError branch lazily imports GrepAstNotAvailableError). README badge/contributing/lineage updated 407→409 to match. Full suite: 409 passed, 1 skipped (Windows-only), 93 subtests. Supersedes the 407-count entry.

[2026-09-20] [README counts] [pass-with-fixes] Round 17: 409→412 (3 new tests in tests/test_review_round17.py: Mermaid node-ID collisions — positional n0/n1/... IDs replace path-derived IDs; Mermaid label breakout — quotes/newlines/pipes escaped; MCP scan-warning cross-talk — discovery warning snapshotted synchronously before any await). Docs were updated 407→409 in the same commit (the 407 baseline was already stale by one). Full suite: 412 passed, 1 skipped (Windows-only), 93 subtests.

[2026-09-20] [README counts] [pass-with-fixes] Static audit 17b: 412→417 (5 new tests in tests/test_static_audit.py: _attach_scan_warning's _UNSET sentinel — explicit None beats the process-global fallback; no-discovery paths pass explicit None). Docs not updated in that commit. Full suite: 417 passed, 1 skipped (Windows-only), 93 subtests.

[2026-09-20] [README counts] [pass-with-fixes] Round 18: 417→420 (3 new tests in tests/test_review_round18.py: per-file tags diskcache and file-text cache now key on stat_fingerprint() (size, mtime_ns) instead of float getmtime() — round 16 fixed file_state/the dirty-diff but left this cache serving stale tags/text on same-size sub-~238ns edits; warm-DB no-dirty scan keeps tagless files in `included` so untagged_files/"Other files" no longer vanish after the first scan; DBStore.populate_refs now takes the store lock like every other write method). Badge/contributing/lineage/AGENTS.md updated 409→420 to match the measured suite. Full suite: 420 passed, 1 skipped (Windows-only), 93 subtests. Supersedes the 409-count entry.
