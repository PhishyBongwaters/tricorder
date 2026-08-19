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