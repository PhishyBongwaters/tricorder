# Tricorder — Code Intelligence Scanner (CLI + MCP Server)

Tricorder is a code-intelligence scanner in the spirit of the *Star Trek* tricorder: point it at a codebase and it reads only what matters. It scans for symbols, signatures, references, and cross-file call graphs, then generates a compact "map" of the repository — highlighting important files, definitions, and their relationships. It runs as both a **command-line application** for on-demand analysis and an **MCP (Model Context Protocol) server** for continuous repository mapping used by LLM clients.

Leverages **tree-sitter** for accurate code parsing and the **PageRank** algorithm to rank code elements by importance, so the most relevant information is always prioritized. A full-repo map typically costs ~1.5% of the tokens of reading every file.

## Status

Full rebrand of the maintained, bug-fixed RepoMapper fork. All upstream bugs resolved; test suite passes.

- **Test Coverage:** 73 tests passing (token_count, Tricorder, caching, MCP path handling, T0/T1 context, noise filter, mermaid-top, exclude-untagged, quiet mode, gitignore filtering, search, import tracking) — `pytest tests/ -q`
- **Python 3.11+** compatible
- **Fixed:** 8 critical upstream bugs (NameError, TypeError, cache path, duplicate definitions, dead variables, redundant checks, dedup edge cases, relative_to crash)

## Benchmark: Tricorder vs Full Repo Scan

| Approach | Chars | Tokens |
|----------|-------|--------|
| Tricorder (definitions only) | 1,702 | 491 |
| Full repo (all files) | 133,432 | 32,620 |
| **Savings** | **131,730 chars** | **32,129 tokens (98.5%)** |

Tricorder output is ~1.5% of full repo size. Savings grow with repo size since the map captures definitions (and optionally reference context), not full file contents.

## Table of Contents
- [Lineage & Attribution](#lineage--attribution)
- [Features](#features)
- [Installation](#installation)
- [CLI Usage](#cli-usage)
  - [Basic Usage](#basic-usage)
  - [Advanced Options](#advanced-options)
  - [Optimal Agent Workflow (Lowest Token Cost)](#optimal-agent-workflow-lowest-token-cost)
- [How It Works](#how-it-works)
- [Output Format & Tiers](#output-format--tiers)
- [Dependency Graph (Mermaid)](#dependency-graph-mermaid)
- [Caching](#caching)
- [Supported Languages](#supported-languages)
- [Running as an MCP Server](#running-as-an-mcp-server)
  - [Setup](#mcp-setup)
  - [MCP Tools](#mcp-tools)
- [License](#license)

## Lineage & Attribution

Tricorder is a rebranded fork of the **RepoMapper** fork of **Aider's RepoMap**:

1. **Gen 1 — Aider `RepoMap`** (Paul Gauthier): tree-sitter symbol extraction + PageRank ranking.
2. **Gen 2 — RepoMapper** (Paul Davis `/ pdavis68`): standalone CLI + MCP server, built with Aider + Claude 3.7 + Cline + Gemini 2.5 Pro. Upstream: https://github.com/pdavis68/RepoMapper
3. **Gen 3 — tricorder**: our fork — 8 bug fixes, 73 tests, 10+ language signature extraction, cross-file call graph, Windows compatibility, full rebrand to tricorder.

Lineage is intentionally kept visible. MIT Licensed.

## Features

- **Smart Code Analysis**: tree-sitter parsing for function/class/method/type definitions
- **Relevance Ranking**: PageRank over a file+symbol reference graph
- **Token-Aware**: respects token limits to fit LLM context windows
- **Caching**: persistent on-disk cache for fast subsequent runs
- **Multi-Language**: Python, JavaScript, TypeScript, Java, C/C++, Go, Rust, Ruby, C#, Swift, and more (tree-sitter grammars)
- **Important File Detection**: prioritizes README, requirements.txt, etc.
- **Untagged Files**: config/helpers/imports with no symbols shown separately
- **Line Counts**: each file header shows `(N lines)`
- **Import Tracking**: language-agnostic import parsing (Python, JS/TS, Java, C/C++, Go, Rust) with qualified name resolution — disambiguates `Path()` vs `pathlib.Path()` across files
- **C++ Support**: full symbol extraction — signatures with params/return types, cross-file caller/callee via reference captures, `.h` parsed as C++ for class/method/namespace awareness

## Installation

```bash
# from the repo root
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt    # Windows
# or
uv pip install -e .
```

Entry points installed:
- `tricorder` — CLI
- `tricorder-mcp` — MCP server

## CLI Usage

### Basic Usage

```bash
# Map current directory
tricorder .

# Map a specific directory with a custom token limit
tricorder src/ --map-tokens 2048

# Map specific files
tricorder file1.py file2.py

# Specify chat files (higher priority) vs other files
tricorder --chat-files main.py --other-files src/

# Mentioned files and identifiers
tricorder --mentioned-files config.py --mentioned-idents "main_function"
```

File priority order:
1. `--chat-files`: highest priority — assumed current work.
2. `--mentioned-files`: high priority — explicitly mentioned in context.
3. `--other-files`: lowest priority — additional context.

### Advanced Options

```bash
tricorder . --verbose
tricorder . --force-refresh
tricorder . --model gpt-3.5-turbo
tricorder . --max-context-window 8192
tricorder . --exclude-unranked
tricorder . --mentioned-files config.py --mentioned-idents "main_function"
tricorder . --output map.txt
tricorder . --format json
tricorder . --top 10
tricorder . --mermaid --mermaid-top 30
tricorder . --exclude-untagged
tricorder . --quiet
tricorder . --dry-run --map-tokens 2048
```

### Optimal Agent Workflow (Lowest Token Cost)

1. **Direct Access** (0 map tokens): path known → read directly; symbol known → use `tricorder_detect`/grep. Don't run a full scan for a known symbol.
2. **Architecture / Topography** (~1k–3k tokens): `tricorder . --mermaid` for module/component structure.
3. **Subsystem Symbols (T0)** (~1k–2k tokens): `--tier 0` scoped to `src/sub/`. At ~14 tokens/tag, `--map-tokens 2048` ≈ 140 definitions.
4. **Targeted Reading** (~100–500 tokens): `read_file` with the line numbers found. Direct read beats T1 for a single target.

## How It Works

1. **File Discovery**: scans source files, skipping `.gitignore`d dirs (plus `build/`, `dist/`, `node_modules/`, `__pycache__/`, etc.)
2. **Code Parsing**: tree-sitter extracts definitions/references
3. **Graph Building**: files = nodes, symbol references = edges
4. **Ranking**: PageRank over the graph
5. **Token Optimization**: binary search fits the most important content within token limits
6. **Output Generation**: readable code map

## Output Format & Tiers

- **T0 (default):** definition lines only — minimal tokens, find targets fast
- **T1:** definitions + N lines of surrounding context — verify relevance without loading full files

```bash
tricorder . --tier 0
tricorder . --tier 1 --context-lines 3
tricorder . --tier 1 --context-lines 5 --map-tokens 4096
```

Token budget tuning: T0 renders definition lines only (~14 tokens/tag); T1 renders TreeContext (~350 tokens/tag). Start with `--map-tokens 2048 --tier 0`.

## Dependency Graph (Mermaid)

```bash
tricorder . --mermaid
tricorder . --mermaid --top 10
tricorder --chat-files main.py --other-files src/ --mermaid
```

Nodes = files, edges = symbol references. Chat files highlighted in pink.

## Caching

- Cache directory: `.repomap.tags.cache.v1/`
- Auto-invalidated when files change; cleared with `--force-refresh`
- **Gotcha:** after installing new tree-sitter parsers, maps may be empty from a stale cache — use `--force-refresh` or delete the cache dir.

## Supported Languages

Languages with tree-sitter grammars (via `queries/tree-sitter-language-pack/`): arduino, c, cpp, csharp, c_sharp, chatito, commonlisp, d, dart, elisp, elixir, elm, gleam, go, hcl, javascript, java, kotlin, lua, ocaml, ocaml_interface, php, pony, properties, python, ql, r, racket, ruby, rust, scala, solidity, swift, typescript, udev.

## Running as an MCP Server

### MCP Setup

Tricorder runs as an MCP server over **STDIO**.

### Hermes Agent (primary integration)

Register it under `mcp_servers:` in `~/.hermes/config.yaml`, then restart Hermes (no
hot-reload — a restart is required). The 4 tools appear in every conversation as
`mcp_tricorder_scan`, `mcp_tricorder_detect`, `mcp_tricorder_symbols`,
`mcp_tricorder_detail`.

```yaml
mcp_servers:
  tricorder:
    command: "C:/absolute/path/to/tricorder/.venv/Scripts/tricorder-mcp.exe"
    args: []
```

Requires the `mcp` Python package in the Hermes host (`pip install mcp`). A bundled skill
(`skills/tricorder/SKILL.md`) teaches the agent the scan → detect/symbols → detail workflow.
No plugin code is required — native MCP client is the supported path.

### Other clients (Cline/Roo)

For a client like Cline/Roo, add to `cline_mcp_settings.json`:

```json
{
  "mcpServers": {
    "tricorder": {
      "disabled": false,
      "timeout": 60,
      "type": "stdio",
      "command": "C:/absolute/path/to/tricorder/.venv/Scripts/tricorder-mcp.exe",
      "args": []
    }
  }
}
```

Or run the server directly:

```bash
python tricorder_server.py
```

The server listens over STDIO. Clients call tools with `project_root` as an absolute path.

### MCP Tools

| Tool | Purpose |
|------|---------|
| `tricorder_scan` | Generate a repository map for a project. Param `output_format` = `text` (prioritized definitions) or `mermaid` (dependency flowchart). Param `tier` = `0` (definitions only) or `1` (+ context). Also `token_limit`, `chat_files`, `other_files`, `mentioned_files`/`mentioned_idents`, `exclude_unranked`, `force_refresh`, `max_context_window`, `max_files`, `output_file`, `dry_run`. |
| `tricorder_detect` | Search for identifiers by name across the codebase. Case-insensitive; returns file, line, def/ref kind, context. Params `query`, `max_results`, `context_lines`, `include_definitions`, `include_references`. |
| `tricorder_symbols` | Structured symbol query with type + file filters. Returns full symbol records (name, type, file, line range, signature, docstring, language, tree-sitter kind). Params `query`, `type`, `file`, `limit` (default 50, cap 200). |
| `tricorder_detail` | Deep-dive on a specific symbol — body, callers (cross-file refs), callees. Params `name`, `file`, `line`. |

Example `tricorder_scan` (mermaid):

```json
{
  "tool": "tricorder_scan",
  "arguments": {
    "project_root": "/absolute/path/to/project",
    "output_format": "mermaid",
    "chat_files": ["main.py"],
    "other_files": ["src/"]
  }
}
```

Returns `{"map": "<mermaid flowchart>", "report": {...}}`. Chat files highlighted in pink.

Example `tricorder_symbols`: find auth-related functions → `query="auth", type="function"`; showcase a class → `query="User", type="class"`; all functions in a file → `file="auth.py"`; full repo scan → `query=""`.

## License

MIT. This is based on the RepoMap design from the Aider project; lineage documented above.