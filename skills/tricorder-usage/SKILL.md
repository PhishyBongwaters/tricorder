---
name: tricorder-usage
description: How to use tricorder repo maps — digest injection, MCP tools, map file reading
category: codebase-understanding
---

# Tricorder Usage Protocol

This skill is the operating procedure for tricorder. The plugin injects a short digest on first turn; this skill tells you what to do with it.

When you see a `[tricorder]` digest in your user message, **do not guess** — the map exists and is current. Follow this flow:

## 1. Digest Injection (Auto on First Turn)

```
[tricorder] Active project map ready: /path/to/project (N lines, ~M tokens, tier 0). 
Full map at /path/to/cache/abc123.map. Use /tricorder scan to rebuild, 
the MCP tools (mcp_tricorder_detect/symbols/detail) for targeted probes, 
or read the map file for the symbol skeleton. Do NOT re-scan this turn.
```

This means:
- A repo map exists at the cache path
- It's fresh (stat-hash validated)
- Tier 0 = definitions only (~14 tokens/tag), Tier 1 = with context (~350 tokens/tag)

## 2. Get Symbols — Three Ways

Use these only when the digest points you at a directory, symbol family, or file path. The point is to stay directed before opening the repo.

**A. MCP Tools (preferred for queries)**
```
mcp_tricorder_detect: find symbols matching a pattern
mcp_tricorder_symbols: get details for a symbol (signature, file, line, callers/callees)
mcp_tricorder_detail: deep dive on a symbol
```

**B. Read the `.map` file directly**
```python
read_file("/path/to/cache/abc123.map")
```
Format: `path/to/file.ext:line:kind:symbol` — one per line

**C. Slash Commands (for humans)**
- `/tricorder status` — cache state + all cached projects
- `/tricorder scan [path]` — force rebuild
- `/tricorder root <path>` — set active project

## 3. Example Workflow

User asks: "Where is the SDL window initialized?"

Recommended flow:
1. Read the digest.
2. Use MCP to narrow to the right symbol/file.
3. Pull only the specific file or symbol body you need.
4. Use a full file read as the last restore only when the map and symbol lookup still leave ambiguity.

```python
# 1. Search for SDL init
mcp_tricorder_detect(pattern="SDL_Init|SDL_CreateWindow")

# 2. Get details on hits
mcp_tricorder_symbols(symbol="mainLoop", file="src/sdl-test-ui/projectM_SDL_main.cpp")

# 3. Or read map for context
read_file("/cache/abc123.map")  # grep for SDL
```

## 4. Cache Validity

- Cache is **content-aware** (stat-hash: path+size+mtime per file)
- Auto-rebuilds on file changes — no TTL, no manual invalidation
- Changing `exclude_globs` changes file set → new signature → rebuild

## 5. Don't Do This

- Treat the digest as a full answer; it is direction, not proof.
- Open the whole repo first.
- Jump to a full file pull before trying symbol lookup.
- Re-scan when the digest already points at the right area.

- ��� Guess file locations
- ��� Ask user to run `/tricorder scan` unless map is stale
- ��� Assume symbols without checking the map
- �� Trust the digest → query MCP → answer from evidence