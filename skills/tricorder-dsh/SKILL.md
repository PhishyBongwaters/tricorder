---
name: tricorder
description: Use tricorder (via dsh MCP bridge) to map a codebase (symbols, call graphs, signatures) without reading every file. Use when exploring an unfamiliar repo, locating a definition, or summarizing project structure in deepseek-harness.
whenToUse: Exploring an unfamiliar codebase, locating a symbol definition, tracing callers/callees, or summarizing repo structure with minimal token cost.
---

# Tricorder (deepseek-harness / dsh port)

Downstream port of the Hermes `tricorder` skill for deepseek-harness (dsh).
Source of truth for the underlying knowledge: the Hermes skill at
`skills/tricorder/SKILL.md` in this repo. Keep the two in sync on shared facts
(escalation ladder, arg names, token costs); this file only differs in the
tool-name prefix and the dsh integration plumbing.

## Tool names (dsh MCP bridge)

Tricorder is registered as an MCP server named `tricorder` via `dsh-mcp-client`
(`serverName: tricorder`). dsh prefixes external server tools as
`mcp__<serverName>__<rawName>`, so the tools you call are:

- `mcp__tricorder__tricorder_scan` — project map / structure
- `mcp__tricorder__tricorder_detect` — find an identifier (case-insensitive, cheap)
- `mcp__tricorder__tricorder_symbols` — definition + signature + line
- `mcp__tricorder__tricorder_detail` — full symbol body + cross-file callers/callees
- `mcp__tricorder__tricorder_query` — graph traversal DSL on call graph (callers/callees/refs/defs with depth, exclude, type, limit)

## Install (reproducible)

This skill hybrid-installs: the file lives in-repo under `skills/tricorder-dsh/`
and is copied into dsh's skill dir (dsh can't symlink into a repo checkout).

```bash
# 1. pip-install tricorder (builds the `tricorder-mcp` console script)
pip install -e "D:/Projects/tricorder"

# 2. install this skill into dsh
mkdir -p ~/.dsh/skills/tricorder
cp "D:/Projects/tricorder/skills/tricorder-dsh/SKILL.md" ~/.dsh/skills/tricorder/SKILL.md
```

That yields one skill, version-controlled. Repo copy is source of truth; the
`~/.dsh/skills/tricorder/` copy is a build artifact. Re-copy after edits.

## cordis.yml wiring

Add to the dsh Cordis config (the row that mounts the MCP client). The
`dsh-mcp-client` plugin's stdio schema (from its `src/index.ts`) takes
`serverName`, `command`, `args`, `env`, `cwd`. Put the row in the profile's
`cordis.patch.yml` as an `insert:` entry:

```yaml
- insert:
    - id: mcp-tricorder
      name: '@deepseek-ai/dsh-mcp-client'
      config:
        serverName: tricorder
        transport: stdio
        command: C:/Users/macdo/AppData/Roaming/Python/Python314/Scripts/tricorder-mcp.exe
        args: []
```

`tricorder-mcp` is the console-script entry point from the tricorder
`pyproject.toml`. **It is usually not on PATH**: pip-install puts it under
`%APPDATA%\Python\Python3xx\Scripts\` (here
`C:/Users/macdo/AppData/Roaming/Python/Python314/Scripts/tricorder-mcp.exe`).
Use that absolute path as `command` — robust, recommended. `serverName` must
match `[A-Za-z0-9_-]{1,32}`; `tricorder` is valid.

## When to use

| Situation | Use |
|-----------|-----|
| "How is this project structured?" | `mcp__tricorder__tricorder_scan` (text) |
| Module/component dependency view | `mcp__tricorder__tricorder_scan` with `output_format: mermaid` |
| "Where is `<symbol>` defined?" | `mcp__tricorder__tricorder_detect` or `mcp__tricorder__tricorder_symbols` |
| Callers / callees of one symbol | `mcp__tricorder__tricorder_detail` |
| Graph traversal: callers/callees up to N hops, filtered | `mcp__tricorder__tricorder_query` — `callers('sym') depth=2 exclude=tests/**` |

Don't scan for a known symbol — go straight to `detect`/`symbols`. Scan only for structure.

## Workflow — escalation ladder (stop at the first rung that answers)

The point of tricorder is to NOT read every file. Climb the ladder; stop at the first rung that answers the question. Pulling a full file is the **last resort, not the default**.

1. **T0 map (auto-injected)** — the `[tricorder]` digest at turn 0 already gives the repo skeleton: file paths + symbol names + line numbers. Often enough to know *which* file. **Don't re-scan** — the digest is current.
2. **Locate** — `mcp__tricorder__tricorder_detect {query}` (case-insensitive, token-cheap) or `mcp__tricorder__tricorder_symbols {query, file?, type?}` for a definition + signature + line. Returns the what/where without reading the file.
3. **Graph query** — need callers/callees up to N hops? `mcp__tricorder__tricorder_query {query: "callers('sym') depth=2 exclude=tests/**"}` returns the exact subgraph in one call (nodes + edges), replacing 5+ round-trips.
4. **Deep-dive** — `mcp__tricorder__tricorder_detail {name, file, line}` returns the **full symbol body** + cross-file callers/callees. For most "how does X work" questions this is enough — you get the implementation, not just the signature.
5. **Escalate the map tier** — `mcp__tricorder__tricorder_scan {project_root, tier: 1, context_lines: 3}` gives definitions + surrounding lines (~350 tokens/tag, ~25x T0). Use `output_format: "mermaid"` for a module dependency graph.
6. **Full file read — last resort** — only when all of the above left genuine ambiguity. Read the *specific line range* found in step 2/3, not the whole file blindly. A whole-file pull is a confession that the ladder failed.

**Token economics**: T0 ≈ 14 tokens/tag. T1 ≈ 350 tokens/tag. `detail` returns one symbol body (typically 50-400 tokens). A full file read is thousands. Escalate deliberately.

### Required param

All MCP tools require `project_root` (absolute path) — they route against that root, so pass the real filesystem path.

## tricorder_scan parameters

- `project_root` (required), `token_limit` (default 8192), `tier`: `0` = definitions only (default) or `1` = + context lines
- `output_format`: `text` or `mermaid`; `chat_files`, `other_files`, `mentioned_files`, `mentioned_idents`
- `exclude_unranked`, `exclude_untagged`, `force_refresh`, `dry_run`, `max_files`
- `exclude_globs`: list of glob patterns (relative, POSIX) to drop from the auto-scan before ranking. Use for vendored/third-party subtrees, e.g. `["vendor/**"]`. Ignored when `other_files` is explicitly provided.

## CLI reference

The standalone CLI is harness-independent and works the same under dsh:

```bash
tricorder . --map-tokens 2048                # map cwd
tricorder src/ --tier 1 --context-lines 3    # T1 with context
tricorder --chat-files main.py --other-files src/ --mermaid
tricorder --force-refresh .                  # bust stale tag cache
tricorder --exclude-globs vendor/** third_party/** .  # skip vendored code
```

Tier tokens: T0 ≈ 14 tokens/tag (definitions), T1 ≈ 350 tokens/tag (with context).

## Multi-project caching

The scanner caches maps per-project in the **scanned project's root** as
`.repomap.tags.cache.v1/`. Cache validity is **content-aware**: a stat-based
signature (path + size + mtime per source file, sha256'd) is stored in the meta
JSON. On the next access, if the signature matches current stats, the cache is
reused — no rebuild. If files changed, the signature differs and a rebuild
happens automatically. Passing `force_refresh: true` (or `--force-refresh`)
busts the cache explicitly, and changing `exclude_globs` changes the file set →
different signature → auto-rebuild.

## Don't — discipline

- **Don't pull a full file before trying `detect` → `symbols` → `detail`.** The ladder exists because `detail` returns the body at a fraction of the cost.
- **Don't treat the digest as a full answer.** It's direction, not proof.
- **Don't open the whole repo first.** Use the map to narrow.
- **Don't re-scan when the digest already points at the right area.** It's current.
- **Don't guess file locations.** Query MCP.
- **Don't run a full rebuild** unless the map is stale (file changes not reflected).

## Pitfalls

- **Stale cache → empty/odd maps**: after installing new tree-sitter parsers or an upgrade, maps can look wrong from a cached parse. Pass `force_refresh: true` or delete the `.repomap.tags.cache.v1/` dir.
- **Cache is per-project**: it lives in the scanned project's root, not tricorder's — don't ship or commit it.
- `project_root` must be absolute; relative paths are not trusted.
- `tricorder_detect` is case-insensitive and token-cheap — prefer it over a full scan to find an identifier.
- **Arg names are exact** — the tools use strict MCP names, so a wrong guess costs a rejected call. The ones that bite: `tricorder_scan` takes `project_root` (not `files`/`path`), `tricorder_detect` takes `query` (not `identifier`), `tricorder_detail` takes `name`+`file`+`line` (not `symbol`).
- **FastMCP tool names carry the `tricorder_` prefix** (server defines `tricorder_scan`, not `scan`), so the full dsh name is `mcp__tricorder__tricorder_scan` — both the server prefix and the `mcp__tricorder__` bridge prefix appear. Write the full name.
```