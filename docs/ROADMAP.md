# tricorder Roadmap

**Mission**: Context guarding for 16GB VRAM home users — deterministic tooling only (tree-sitter, PageRank, token counting, git diff, file I/O). No model calls inside tricorder.

**Current State**: RC1 — 5 MCP tools (incl. `tricorder_query` graph traversal), lifecycle plugin, skill, 10-language coverage, content-aware caching, slash commands. All verified working.

---

## Completed

### M0.9.1 - Token Budget Fields ✅ DONE
- MCP tools: `token_estimate`, `full_repo_estimate`, `savings_pct` added to all 5 tools
- CLI: `--stats-only <map>` + `--format json` budget fields implemented
- Plugin: `/tricorder status` surfaces savings vs full-repo via venv delegation

### M0.9.2 - Tier Escalation Signal ✅ DONE
- `tricorder_scan` returns `tier_hint` in `dry_run` and `output_file` paths when `tags_at_budget < total_tags`
- `tier_hint` message: "T0 incomplete: X/Y tags fit (Z%). Consider tier=1 or higher token_limit."
- Also retains upgrade advisory from `_tier_history` (T0→T1)
- Test: `tests/test_mcp.py::TestMCPOutputFile::test_output_file_tier_hint_on_upgrade` passes.

---

## Milestone 0.10 — Graph Query MCP Tool (P0) ✅ DONE

*Target: Single MCP tool replacing 5+ round-trips for common agent graph traversals.*

### M0.10.1 — `tricorder_query` MCP Tool — SHIPPED
**Scope**: New MCP tool accepting graph traversal DSL → returns precise subgraph (nodes + edges) in one call. Reuses existing call graph (`build_call_graph`) and cross-file resolution (`name_resolver`).

**DSL Grammar**:
```
query := traversal (pipe traversal)*
traversal := "callers" | "callees" | "refs" | "defs"
pipe := "|" traversal
modifiers := "depth=" INT | "exclude=" GLOB | "include=" GLOB | "type=" ("function"|"class"|"method"|"variable") | "limit=" INT
```

**Examples**:
- `callers('authenticate') depth=2` — all callers up to 2 hops
- `callees('main') depth=1 exclude=tests/**` — direct callees, skip tests
- `refs('Config') type=class limit=50` — all references to class Config
- `callers('foo') | callees('bar') depth=3` — chained traversals

**Files**:
- `tricorder_server.py` — `@mcp.tool() tricorder_query` (registered)
- `utils.py` — `parse_query_dsl(dsl: str) -> ParsedQuery` (hand-rolled, no lark dep)
- `core.py` — `query_graph(dsl: str) -> dict` (BFS on call graph + filter)
- `tests/test_graph_query.py` — new test file

**Dependencies**: None — reuses existing `TAGS_CACHE`, `build_call_graph`, `get_symbol_detail`, import index.

**Definition of Done** (all checked at merge):
- [x] `tricorder_query` registered in `tricorder_server.py`
- [x] DSL parser handles all grammar forms
- [x] BFS traversal respects depth, exclude, type, limit
- [x] Response includes `token_estimate`, `full_repo_estimate`, `savings_pct`
- [x] All 10 test cases pass (24 sub-assertions across 10 cases, `tests/test_graph_query.py`)
- [x] SPEC.md updated with tool documentation
- [x] CHANGELOG entry

*Result: M0.10 closed — single-call graph traversal (callers/callees/refs/defs, chained via `|`, depth/exclude/type/limit modifiers) verified by 24 passing tests. Delivers the 5+ round-trip reduction it was scoped for.*

---

## Non-Goals (Explicitly Out of Scope)

- Git/VCS dependence — tricorder maps any directory, git or not; no `git diff`/incremental rebuild
- AI summarization of symbols
- Natural language → symbol mapping (embeddings)
- Auto-tier selection by query heuristics
- Semantic/vector code search
- Package manager dependency resolution (npm, cargo, go.mod, pip)
- Cloud/remote scanning
- LSP / editor integration — agents use MCP, not LSP
- Watch daemons / background polling — editor triggers refresh if needed
- Multi-root workspaces — single project per scan

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