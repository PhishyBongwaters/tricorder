# Plugins and skills — turn-0 injection and agent guidance

Source of truth: the code. Every claim below names its file.

Two hosts, same pattern: inject orientation at session start, expose
on-demand access after. The digest text is owned by the tricorder CLI
(`--probe-digest`), so both plugins inject byte-identical turn-0
content from one code path.

## 1. Hermes plugin (`plugins/tricorder/__init__.py`)

- Turn-0 injection: digest or DB coverage for the active project,
  cached with signature validation (`_is_cache_valid`,
  `_project_signature`, `_cache_age_str`).
- Slash commands for on-demand access:
  `/tricorder scan|find|detail|root|status` (plugin docstring, line
  13). `scan` shells the CLI with `--db-path` at the canonical
  in-repo DB, so slash scans populate the same sqlite the MCP tools
  and `chunk_resume.py` read.
- Runs the CLI through the project's venv over subprocess; the
  plugin never imports tricorder code directly.

## 2. Hermes skill (`skills/tricorder/SKILL.md`)

Registered as `codebase-tricorder`. Teaches agents when to reach for
tricorder (unfamiliar repo, locating a definition, summarizing
structure), a situation-to-tool table (structure → scan, definition
→ detect/symbols, callers → detail, multi-hop → query), and the
escalation ladder: auto-injected T0 digest, locate, graph query,
deep-dive detail, tier escalation, full file read last. All MCP
tools require an absolute `project_root`.

## 3. DSH plugin (`plugins/dsh-tricorder-inject/`, npm
`@deepseek-ai/dsh-tricorder-inject`)

Turn-0 probe-digest injection for DeepSeek Harness sessions
(`src/index.ts`, `invariant.ts`). On session creation it runs the
shared `--probe-digest` CLI flag and injects the navigation digest
as a plugin-sourced message before the first turn. A navigation
item, not a deep dive: a fast tally that never builds the full map,
which is produced on demand via `/tricorder scan` or the MCP tools.

## 4. DSH skill (`skills/tricorder-dsh/SKILL.md`)

Same shape as the Hermes skill — situation table, escalation ladder,
required `project_root` — with tool names in the DSH convention
(`mcp_tricorder_scan`, `mcp_tricorder_detect`,
`mcp_tricorder_symbols`, `mcp_tricorder_detail`).
