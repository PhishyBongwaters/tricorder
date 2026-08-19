# tricorder Roadmap

**Mission**: Context guarding for 16GB VRAM home users — deterministic tooling only (tree-sitter, PageRank, token counting, git diff, file I/O). No model calls inside tricorder.

**Current State**: RC1 — 4 MCP tools, lifecycle plugin, skill, 10-language coverage, content-aware caching, slash commands. All verified working.

---

## Milestone 0.9 — Context Guarding Hardening (P0)

*Target: Before 1.0 release. Every item directly serves the mission.*

### M0.9.1 — Token Budget Fields in MCP Responses
**Scope**: Add `token_estimate`, `full_repo_estimate`, `savings_pct` to all 4 MCP tool responses.
**Files**: `tricorder_server.py` (4 tool handlers)
**Validation Gate**:
```bash
# Each tool returns budget fields
tricorder_scan:   has token_estimate, full_repo_estimate, savings_pct
tricorder_detail: has token_estimate, full_repo_estimate, savings_pct
tricorder_symbols: has token_estimate, full_repo_estimate, savings_pct
tricorder_detect:  has token_estimate, full_repo_estimate, savings_pct
```
**Test**: `python -m pytest tests/test_token_budget_fields.py -v`

---

## M0.9.2 — Tier Escalation Signal
**Scope**: `tricorder_scan` returns `tier_hint` when `tags_at_budget < total_tags` (T0 incomplete).
**Files**: `tricorder_server.py:tricorder_scan` (dry_run and output_file paths)
**Validation Gate**:
```bash
# Scan with token_limit=1024 forcing truncation (dry_run or output_file)
# Response must contain tier_hint string mentioning T0 coverage %
```
**Test**: `python -m pytest tests/test_mcp.py::TestMCPOutputFile::test_output_file_tier_hint_on_upgrade -v`

---

### M0.9.3 — Model Context-Window Awareness
**Scope**: Plugin reads `model.max_tokens` from hook context → scales `_MAP_TOKENS` proportionally.
**Files**: `plugins/tricorder/__init__.py` (`_MAP_TOKENS`, `_on_pre_llm_call`)
**Validation Gate**:
```bash
# Hook receives model={"max_tokens": 4096} → _MAP_TOKENS becomes 1024
# Hook receives model={"max_tokens": 131072} → _MAP_TOKENS becomes 8192
# Formula: min(max(model_max * 0.25, 1024), 8192)
```
**Test**: `python -m pytest tests/test_context_window_scaling.py -v`

---

~~M0.9.4 — Git-Diff Incremental Rebuild~~ REMOVED
No git dependence. tricorder does not assume a project is a git repo and never
requires git to map a codebase. Incremental rebuilds are out of scope.

---

### M0.9.5 — Cross-Project Unified Scan
**Scope**: New MCP tool `tricorder_multi_scan(project_roots: list[str], ...)` merges ranked tags across roots.
**Files**: `tricorder_server.py` (new `@mcp.tool`), `core.py` (multi-root ranking)
**Validation Gate**:
```bash
# tricorder_multi_scan(project_roots=["/projA", "/projB"], token_limit=2048)
# Returns unified map with tags from both, re-ranked by global PageRank
# token_estimate ≤ 2048
```
**Test**: `python -m pytest tests/test_multi_scan.py -v`

---

### M0.9.6 — Verification Artifact
**Scope**: `tricorder --verify <map_file>` re-tokenizes output, emits `{"map_tokens": N, "original_estimate": M, "diff_pct": X}`.
**Files**: `tricorder.py` (new `--verify` flag), `utils.count_tokens`
**Validation Gate**:
```bash
# tricorder . --map-tokens 2048 --output map.txt
# tricorder --verify map.txt
# Output: map_tokens=1987, original_estimate=2048, diff_pct=3.0
# Assert: diff_pct < 5%
```
**Test**: `python -m pytest tests/test_verify_artifact.py -v`

---

## Milestone 1.0 — Scale & Usability (P1)

*Target: Post-1.0, enables larger repos and smoother daily use.*

### M1.1 — Language Parity: 10 Additional Languages
**Scope**: Add tree-sitter query files (`.scm`) for signature + return type extraction.
**Languages**: Zig, Nim, Kotlin, Scala, Haskell, OCaml, Elixir, Erlang, Dart, Lua
**Files**: `queries/tree-sitter-language-pack/<lang>-tags.scm` (10 new files)
**Validation Gate**:
```bash
# For each new lang: test file with function + return type → tricorder_symbols returns signature with return type
# 73 existing tests + 10 new lang tests = 83 tests green
```
**Test**: `python -m pytest tests/test_language_parity.py -v`

---

### M1.2 — Binary/Large-File Guard
**Scope**: Explicit `--max-file-size-mb` CLI arg (default 1MB), skip + log.
**Files**: `tricorder.py`, `scm.py:discover_src_files`, `core.py:Tricorder`
**Validation Gate**:
```bash
# Create 5MB .py file → tricorder . --max-file-size-mb 1 → file skipped, logged
# Default (no flag) → 1MB limit enforced
```
**Test**: `python -m pytest tests/test_max_file_size.py -v`

---

### M1.3 — Parallel Parse
**Scope**: `ThreadPoolExecutor` over `get_tags` in `core.py:Tricorder.get_ranked_tags`.
**Files**: `core.py` (import concurrent.futures, pool size = min(8, cpu_count))
**Validation Gate**:
```bash
# 1500-file repo: sequential parse time T1, parallel parse time T2
# Assert: T2 < T1 * 0.4 (2.5x+ speedup)
# Assert: output map identical (tag order may differ, content same)
```
**Test**: `python -m pytest tests/test_parallel_parse.py -v`

---

### M1.4 — Editor-Triggered Incremental Refresh
**Scope**: `tricorder refresh <file> --root <project>` invalidates single-file cache entry, re-parses, rebuilds map. Editor integration via on-save hooks (VS Code task, Neovim autocmd, Zed task, shell alias). No daemon, no watchdog, no polling.
**Files**: `tricorder.py` (new `refresh` subcommand), `core.py` (`refresh_files()`), `docs/editor-integration.md`
**Validation Gate**:
```bash
# tricorder refresh file.py --root /project --quiet
# Editor save → sub-second map update
# tricorder refresh --all --root /project → full cache refresh
```
**Test**: `python -m pytest tests/test_refresh_mode.py -v`

---

### M1.5 — Language Server Protocol (LSP) Server
**Scope**: New entry point `tricorder-lsp` exposing code intelligence via standard LSP — Go to Definition, Find References, Hover, Document Symbols, Workspace Symbols. Read-only on tricorder cache; editors (VS Code, Neovim, Zed, Helix) work out of the box.
**Files**: `tricorder_lsp.py` (new), `pyproject.toml` (entry point), `requirements.txt` (+pygls, lsprotocol), `docs/lsp-setup.md`
**Validation Gate**:
```bash
# tricorder-lsp --root /project --stdio
# Editor: gd → jumps to definition (cross-file)
# Editor: gr → lists all references (cross-file)
# Editor: hover → signature + docstring + body preview
# Editor: outline → document symbols
# Editor: workspace symbol search → fuzzy finds across project
```
**Test**: `python -m pytest tests/test_lsp.py -v`

---

## Milestone 1.1 — Polish (P2)

*Target: Quality-of-life, no mission-critical impact.*

### M1.1.1 — Mermaid Graph Filtering
**Scope**: `min_pagerank` threshold in `to_mermaid` (drop nodes below threshold).
**Files**: `core.py:Tricorder.to_mermaid`
**Validation Gate**:
```bash
# tricorder . --mermaid --min-pagerank 0.01 → graph excludes noise nodes
# Node count < default graph node count
```
**Test**: `python -m pytest tests/test_mermaid_filter.py -v`

---

### M1.1.2 — Symbol Kind Filter in Detail
**Scope**: `tricorder_detail` accepts `include_kinds: ["call", "ref", "type"]` filter.
**Files**: `tricorder_server.py:tricorder_detail`, `core.py:get_symbol_detail`
**Validation Gate**:
```bash
# tricorder_detail(..., include_kinds=["call"]) → only callers returned, no type refs
# tricorder_detail(..., include_kinds=["type"]) → only type references
```
**Test**: `python -m pytest tests/test_detail_kind_filter.py -v`

---

### M1.1.3 — Config-Driven exclude_globs Per Tool
**Scope**: Add `exclude_globs` param to `tricorder_detect`, `tricorder_symbols`, `tricorder_detail` (already in `tricorder_scan`).
**Files**: `tricorder_server.py` (3 tool signatures)
**Validation Gate**:
```bash
# tricorder_detect(..., exclude_globs=["vendor/**"]) → no results from vendor/
# tricorder_symbols(..., exclude_globs=["third_party/**"]) → no symbols from third_party/
```
**Test**: `python -m pytest tests/test_exclude_globs_all_tools.py -v`

---

## Release Criteria per Milestone

| Milestone | All Validation Gates Pass | Test Suite Green | Docs Updated (SPEC.md) | CHANGELOG Entry |
|-----------|---------------------------|------------------|------------------------|-----------------|
| M0.9.x    | ✅ Required               | ✅ Required      | ✅ Required            | ✅ Required     |
| M1.x      | ✅ Required               | ✅ Required      | ✅ Required            | ✅ Required     |
| M1.1.x    | ✅ Required               | ✅ Required      | Optional               | ✅ Required     |

---

## Non-Goals (Explicitly Out of Scope)

- Git/VCS dependence — tricorder maps any directory, git or not; no `git diff`/incremental rebuild
- AI summarization of symbols
- Natural language → symbol mapping (embeddings)
- Auto-tier selection by query heuristics
- Semantic/vector code search
- Package manager dependency resolution (npm, cargo, go.mod, pip)
- Cloud/remote scanning

---

## Assignment Template (for team)

```markdown
## M0.9.x — <Title>
**Assignee**: @username
**Branch**: `feature/m0.9.x-<slug>`
**Target Date**: YYYY-MM-DD
**Depends On**: (none | M0.9.y)
**Validation**: Run `python -m pytest tests/test_<gate>.py -v`
**Definition of Done**: All gates pass + SPEC.md updated + CHANGELOG entry
```

## M0.9.1 - Token Budget Fields
- MCP tools: `token_estimate`, `full_repo_estimate`, `savings_pct` added.
- CLI: `--stats-only <map>` + `--format json` budget fields implemented.
- Plugin: `/tricorder status` surfaces savings vs full-repo via venv delegation.
- Tests: 84/84 pass.

## M0.9.2 - Tier Escalation Signal ✅ DONE
- `tricorder_scan` returns `tier_hint` in `dry_run` and `output_file` paths when `tags_at_budget < total_tags`
- `tier_hint` message: "T0 incomplete: X/Y tags fit (Z%). Consider tier=1 or higher token_limit."
- Also retains upgrade advisory from `_tier_history` (T0→T1)
- Test: `tests/test_mcp.py::TestMCPOutputFile::test_output_file_tier_hint_on_upgrade` passes
- All 87 tests pass.