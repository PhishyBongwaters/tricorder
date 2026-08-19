# tricorder Roadmap

**Mission**: Context guarding for 16GB VRAM home users — deterministic tooling only (tree-sitter, PageRank, token counting, git diff, file I/O). No model calls inside tricorder.

**Current State**: RC1 — 4 MCP tools, lifecycle plugin, skill, 10-language coverage, content-aware caching, slash commands. All verified working.

---

## Completed

### M0.9.1 - Token Budget Fields ✅ DONE
- MCP tools: `token_estimate`, `full_repo_estimate`, `savings_pct` added to all 4 tools
- CLI: `--stats-only <map>` + `--format json` budget fields implemented
- Plugin: `/tricorder status` surfaces savings vs full-repo via venv delegation
- Tests: 84/84 pass

### M0.9.2 - Tier Escalation Signal ✅ DONE
- `tricorder_scan` returns `tier_hint` in `dry_run` and `output_file` paths when `tags_at_budget < total_tags`
- `tier_hint` message: "T0 incomplete: X/Y tags fit (Z%). Consider tier=1 or higher token_limit."
- Also retains upgrade advisory from `_tier_history` (T0→T1)
- Test: `tests/test_mcp.py::TestMCPOutputFile::test_output_file_tier_hint_on_upgrade` passes
- All 87 tests pass.

---

## Milestone 0.10 — Graph Query MCP Tool (P0)

*Target: Single MCP tool replacing 5+ round-trips for common agent graph traversals.*

### M0.10.1 — `tricorder_query` MCP Tool
**Scope**: New MCP tool accepting graph traversal DSL → returns precise subgraph (nodes + edges) in one call. Reuses existing call graph (`build_call_graph`) and cross-file resolution (`name_resolver`).

**DSL Grammar** (parse with `lark` or hand-rolled):
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
- `tricorder_server.py` — new `@mcp.tool() tricorder_query`
- `core.py` — `query_graph(dsl: str) -> dict` (BFS on call graph + filter)
- `utils.py` — `parse_query_dsl(dsl: str) -> QueryAST` (new)
- `tests/test_graph_query.py` — new test file

**Validation Gates**:
```bash
# 1. Basic callers traversal
echo 'callers("main") depth=2' | tricorder_query --root /proj
# Returns: {"nodes": [...], "edges": [...], "token_estimate": N, "savings_pct": X}

# 2. Exclude glob filtering
tricorder_query 'callees("Config") exclude=tests/**' --root /proj
# No nodes from tests/ in response

# 3. Depth limiting
tricorder_query 'callers("foo") depth=1' --root /proj
# Only direct callers (not callers-of-callers)

# 4. Type filter
tricorder_query 'refs("User") type=class' --root /proj
# Only class references, not variable/function refs

# 5. Chained traversal
tricorder_query 'callers("auth") | callees("login") depth=2' --root /proj
# Two-phase traversal, combined result

# 6. Token budget respected
tricorder_query 'callers("x") depth=10' --root /proj --token-limit 1024
# Response token_estimate <= 1024, truncates with tier_hint
```

**Test**: `python -m pytest tests/test_graph_query.py -v`

**Test Coverage Requirements**:
| Test | Description |
|------|-------------|
| `test_basic_callers` | Single-hop callers returns correct nodes/edges |
| `test_depth_2` | Two-hop includes callers-of-callers |
| `test_exclude_glob` | `exclude=tests/**` removes test files from result |
| `test_type_filter` | `type=function` filters node kinds |
| `test_limit` | `limit=10` caps nodes returned |
| `test_chained` | `callers | callees` composes correctly |
| `test_token_budget` | `token_limit` truncates with `tier_hint` |
| `test_not_found` | Unknown symbol returns empty + error field |
| `test_cross_file` | Callers/callees include cross-file edges (`cross_file: true`) |
| `test_performance` | 1500-file repo query < 500ms |

**Dependencies**: None — reuses existing `TAGS_CACHE`, `build_call_graph`, `get_symbol_detail`, import index.

**Definition of Done**:
- [ ] `tricorder_query` registered in `tricorder_server.py`
- [ ] DSL parser handles all grammar forms
- [ ] BFS traversal respects depth, exclude, type, limit
- [ ] Response includes `token_estimate`, `full_repo_estimate`, `savings_pct`
- [ ] All 10 test cases pass
- [ ] SPEC.md updated with tool documentation
- [ ] CHANGELOG entry

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