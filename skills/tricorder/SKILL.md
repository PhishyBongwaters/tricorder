---
name: tricorder
description: Use tricorder to map a codebase (symbols, call graphs, signatures) without reading every file. Highest-value when exploring an unfamiliar repo, locating a definition, or summarizing structure.
---

# Tricorder

Use tricorder when you need `symbols`, `signatures`, `callers/callees`, or a compact **map** of a codebase without reading every file. It scans with tree-sitter, ranks by PageRank, and returns only the important definitions — typically **~1.5% of full-repo token cost**.

It is surfaced two ways:

- **Native MCP tools** (primary): when tricorder is registered as an MCP server, its tools appear as `mcp_tricorder_scan`, `mcp_tricorder_detect`, `mcp_tricorder_symbols`, `mcp_tricorder_detail`.
- **CLI**: `tricorder . --map-tokens <N>` for ad-hoc runs without the MCP server.

## When to use

| Situation | Use |
|-----------|-----|
| "How is this project structured?" | `mcp_tricorder_scan` (text) |
| Module/component dependency view | `mcp_tricorder_scan` with `output_format: mermaid` |
| "Where is `<symbol>` defined?" | `mcp_tricorder_detect` or `mcp_tricorder_symbols` |
| Callers / callees of one symbol | `mcp_tricorder_detail` |

Don't scan for a known symbol — go straight to `detect`/`symbols`. Scan only for structure.

## Workflow (lowest token cost)

1. **Topography** (optional): `mcp_tricorder_scan {project_root, output_format: "mermaid"}` — get the module structure once.
2. **Locate**: `mcp_tricorder_symbols {query, file?, type?}` or `mcp_tricorder_detect {query}` for a definition/line.
3. **Deep-dive**: `mcp_tricorder_detail {name, file, line}` for body + cross-file callers/callees.
4. **Read the actual code**: `read_file` at the line numbers found. Direct read beats a full scan for a single target.

### Required param

All MCP tools require `project_root` (absolute path) — they route against that root, so pass the real filesystem path.

## tricorder_scan parameters

- `project_root` (required), `token_limit` (default 8192), `tier`: `0` = definitions only (default) or `1` = + context lines
- `output_format`: `text` or `mermaid`; `chat_files`, `other_files`, `mentioned_files`, `mentioned_idents`
- `exclude_unranked`, `exclude_untagged`, `force_refresh`, `dry_run`, `max_files`

## CLI reference

```bash
tricorder . --map-tokens 2048                # map cwd
tricorder src/ --tier 1 --context-lines 3    # T1 with context
tricorder --chat-files main.py --other-files src/ --mermaid
tricorder --force-refresh .                  # bust stale tag cache
```

Tier tokens: T0 ≈ 14 tokens/tag (definitions), T1 ≈ 350 tokens/tag (with context).

## Pitfalls

- **Stale cache → empty/odd maps**: after installing new tree-sitter parsers or an upgrade, maps can look wrong from a cached parse. Run `--force-refresh` (MCP: `force_refresh: true`) or delete the `.repomap.tags.cache.v1/` dir.
- **Cache is per-project**: it lives in the scanned project's root, not tricorder's — don't ship or commit it.
- `project_root` must be absolute; relative paths are not trusted.
- `tricorder_detect` is case-insensitive and token-cheap — prefer it over a full scan to find an identifier.