# Tricorder — Code Intelligence Scanner (CLI + MCP Server)

Tricorder is a code-intelligence scanner in the spirit of the *Star Trek* tricorder: point it at a codebase and it reads only what matters. It scans for symbols, signatures, references, and cross-file call graphs, then generates a compact "map" of the repository — highlighting important files, definitions, and their relationships. It runs as a **command-line application**, an **MCP (Model Context Protocol) server**, and a **Hermes plugin**. All three surfaces share the same lean map policy: prioritize navigation value, skip obvious noise, and avoid dumping the whole tree.

Leverages **tree-sitter** for accurate code parsing and the **PageRank** algorithm to rank code elements by importance, so the most relevant information is always prioritized. A full-repo map typically costs ~1.5% of the tokens of reading every file.

## Status

**Release Candidate 1** — Full rebrand of the maintained, bug-fixed RepoMapper fork. All upstream bugs resolved; test suite passes.

- **Test Coverage:** 115 tests passing (token_count, Tricorder, caching, MCP path handling, T0/T1 context, noise filter, mermaid-top, exclude-untagged, quiet mode, gitignore filtering, search, import tracking, graph query DSL, CLI autodiscovery, cross-surface budget parity, token budget fields) — `pytest tests/ -q`
- **Python 3.11+** compatible
- **Fixed:** 8 critical upstream bugs (NameError, TypeError, cache path, duplicate definitions, dead variables, redundant checks, dedup edge cases, relative_to crash)
- **Language Coverage:** 10 languages with signature extraction + return types (Python, JS/TS, C, C++, Java, Go, Rust, Swift, C#, Ruby)
- **Cross-file call graph** with import resolution across files
- **MCP Server** with 5 tools: `tricorder_scan`, `tricorder_symbols`, `tricorder_detect`, `tricorder_detail`, `tricorder_query`
- **Hermes Lifecycle Plugin** — auto-injects T0 map on session start, registers `/tricorder` slash commands
- **DSH Skill** — downstream port for deepseek-harness MCP bridge

## Benchmark: Tricorder vs Full Repo Scan

| Approach | Chars | Tokens |
|----------|-------|--------|
| Tricorder (definitions only) | 1,702 | 491 |
| Full repo (all files) | 133,432 | 32,620 |
| **Savings** | **131,730 chars** | **32,129 tokens (98.5%)** |

Tricorder output is ~1.5% of full repo size. Savings grow with repo size since the map captures definitions (and optionally reference context), not full file contents.

### Tricorder Efficacy (Real-World Benchmark Results)

Proven across 2 real repos with 8 realistic agent tasks using two benchmark suites:

| Repo | Tasks | Suite | Map Tokens | Full Repo | Savings |
|------|-------|-------|------------|-----------|---------|
| projectm | 2/2 | bench_validity.py | 2,048 | 642,428 | 99.7% |
| projectm | 2/2 | bench_validity_mcp.py | 2,048 | 642,428 | 99.9% (MCP) |
| vaultwarden | 2/2 | bench_validity.py | 32,563 | 755,518 | 95.7% |
| vaultwarden | 2/2 | bench_validity_mcp.py | 32,563 | 755,518 | 99.6% (MCP) |

**RESULT: ALL TASKS PASS** — both benches confirm the tricorder T0 map (and MCP tools) steer agents to correct code without reading the full repo.

- **projectm** (~5,800 files, ~1.126K lines): ~100% token savings; 2K-token map covers all required identifiers (PCM::AddToBuffer, Loudness, CurrentRelative, AverageRelative)
- **vaultwarden** (~200 Rust files): ~96-99.8% token savings; 33K-token map covers all required identifiers (generate_invite, delete_user, admin_page, hash_password, verify_password_hash, routes, catchers)

*T0 maps and MCP tools (detect/symbols) provide massive token savings while retaining full task coverage. Both CLI and MCP surfaces are effective.*

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
- [Hermes Lifecycle Plugin](#hermes-lifecycle-plugin)
- [DSH Integration](#dsh-integration)
- [License](#license)

## Lineage & Attribution

Tricorder is a rebranded fork of the **RepoMapper** fork of **Aider's RepoMap**:

1. **Gen 1 — Aider `RepoMap`** (Paul Gauthier): tree-sitter symbol extraction + PageRank ranking.
2. **Gen 2 — RepoMapper** (Paul Davis `/ pdavis68`): standalone CLI + MCP server, built with Aider + Claude 3.7 + Cline + Gemini 2.5 Pro. Upstream: https://github.com/pdavis68/RepoMapper
3. **Gen 3 — tricorder**: our fork — 8 bug fixes, 115 tests, 10-language signature extraction, cross-file call graph, Windows compatibility, full rebrand to tricorder.

Lineage is intentionally kept visible. MIT Licensed.

## Features

- **Smart Code Analysis**: tree-sitter parsing for function/class/method/type definitions
- **Relevance Ranking**: PageRank over a file+symbol reference graph
- **Token-Aware**: respects token limits to fit LLM context windows
- **Caching**: persistent on-disk cache for fast subsequent runs (content-aware invalidation via stat-based signatures)
- **Multi-Language**: Python, JavaScript, TypeScript, Java, C/C++, Go, Rust, Ruby, C#, Swift, and more (tree-sitter grammars)
- **Important File Detection**: prioritizes README, requirements.txt, etc.
- **Untagged Files**: config/helpers/imports with no symbols shown separately
- **Line Counts**: each file header shows `(N lines)`
- **Import Tracking**: language-agnostic import parsing (Python, JS/TS, Java, C/C++, Go, Rust) with qualified name resolution — disambiguates `Path()` vs `pathlib.Path()` across files
- **C++ Support**: full symbol extraction — signatures with params/return types, cross-file caller/callee via reference captures, `.h` parsed as C++ for class/method/namespace awareness
- **Cross-File Call Graph**: callers/callees with import resolution across files
- **Graph Query DSL**: `callers('sym') depth=2 exclude=tests/**` — replaces 5+ round-trips for call graph exploration
- **Mermaid Graph Output**: dependency flowcharts with chat files highlighted

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

# No paths given? Auto-discovers source files under --root (capped at 1000).
tricorder --root . --map-tokens 2048
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
tricorder . --max-files 5000  # raise auto-discovery cap (default 1000)
tricorder . --exclude-globs vendor/** third_party/**  # skip vendored code before ranking
tricorder . --signature-only  # print content signature for cache validation
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

This same discovery policy is shared by the CLI, MCP server, and Hermes plugin, so a repo that looks lean in one surface looks lean in the others too.

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

- Cache directory: `.repomap.tags.cache.v1/` (in the scanned project's root)
- Auto-invalidated when files change via content-aware signatures (sha256 of path+size+mtime per source file); cleared with `--force-refresh`
- **Gotcha:** after installing new tree-sitter parsers, maps may be empty from a stale cache — use `--force-refresh` or delete the cache dir.
- `--signature-only` prints the 16-char content signature for debugging cache validity.

## Supported Languages

Languages with tree-sitter grammars (via `queries/tree-sitter-language-pack/`): arduino, c, cpp, csharp, c_sharp, chatito, commonlisp, d, dart, elisp, elixir, elm, gleam, go, hcl, javascript, java, kotlin, lua, ocaml, ocaml_interface, php, pony, properties, python, ql, r, racket, ruby, rust, scala, solidity, swift, typescript, udev.

**Signature extraction + return types (10 languages):** Python, JS/TS, C, C++, Java, Go, Rust, Swift, C#, Ruby

## Running as an MCP Server

### MCP Setup

Tricorder runs as an MCP server over **STDIO**.

### Hermes Agent (primary integration)

Register it under `mcp_servers:` in `~/.hermes/config.yaml`, then restart Hermes (no hot-reload — a restart is required). The 5 tools appear in every conversation as `mcp_tricorder_scan`, `mcp_tricorder_detect`, `mcp_tricorder_symbols`, `mcp_tricorder_detail`, `mcp_tricorder_query`.

```yaml
mcp_servers:
  tricorder:
    command: "C:/absolute/path/to/tricorder/.venv/Scripts/tricorder-mcp.exe"
    args: []
```

Requires the `mcp` Python package in the Hermes host (`pip install mcp`). A bundled skill (`skills/tricorder/SKILL.md`) teaches the agent the escalation ladder: T0 map → detect/symbols → detail → tier-1 scan → full-file read (last resort). No plugin code is required — native MCP client is the supported path.

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
| `tricorder_scan` | Generate a repository map for a project. Param `output_format` = `text` (prioritized definitions) or `mermaid` (dependency flowchart). Param `tier` = `0` (definitions only) or `1` (+ context). Also `token_limit`, `chat_files`, `other_files`, `mentioned_files`/`mentioned_idents`, `exclude_unranked`, `exclude_untagged`, `force_refresh`, `max_context_window`, `output_file`, `dry_run`, `exclude_globs` (list of glob patterns, e.g. `["vendor/**"]`, to drop third-party subtrees from the auto-scan before ranking). Returns token budget fields: `token_estimate`, `full_repo_estimate`, `savings_pct`, `tier_hint`. |
| `tricorder_detect` | Search for identifiers by name across the codebase. Case-insensitive; returns file, line, def/ref kind, context. Params `query`, `max_results`, `context_lines`, `include_definitions`, `include_references`. |
| `tricorder_symbols` | Structured symbol query with type + file filters. Returns full symbol records (name, type, file, line range, signature, docstring, language, tree-sitter kind). Params `query`, `type`, `file`, `limit` (default 50, cap 200). |
| `tricorder_detail` | Deep-dive on a specific symbol — body, callers (cross-file refs), callees. Params `name`, `file`, `line`. |
| `tricorder_query` | Graph traversal on the call graph. DSL: `callers('sym') depth=2 exclude=tests/** \| callees('other') type=class`. Returns `{nodes, edges, token_estimate, savings_pct}`. Replaces 5+ round-trips for call graph exploration. |

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

Example `tricorder_query`: find all callers of authenticate up to 2 hops → `query="callers('authenticate') depth=2"`; direct callees of main excluding tests → `query="callees('main') depth=1 exclude=tests/**"`; chained traversal → `query="callers('foo') \| callees('bar') depth=3"`.

## Hermes Lifecycle Plugin

The plugin (`plugins/tricorder/`) is a real Hermes plugin (manifest + `__init__.py` with `register(ctx)`) installed to `~/.hermes/plugins/tricorder/` via `hermes plugins install`. It wires the `on_session_start` + `pre_llm_call` hooks so the active project's T0 map is built once and a compact digest is injected into the first turn's user message — the agent gets the codebase skeleton *before* it acts. It also registers `/tricorder` slash commands and the `tricorder:tricorder` skill.

### Slash Commands

| Command | Description |
|---------|-------------|
| `/tricorder root <path>` | Set the active project (persists to `plugins.entries.tricorder.active_project`). Checks cache: if valid, reports "cache ready." If stale/missing, auto-rebuilds. |
| `/tricorder scan [path]` | Force-rebuild a repo map (default: active project). Ignores signature. |
| `/tricorder status` | Show active project + cache state (valid/stale/missing, age) + all other cached projects. |

### Plugin Config

Both knobs live under `plugins.entries.tricorder.*` in `~/.hermes/config.yaml`:

| Key | Type | Description |
|-----|------|-------------|
| `active_project` | string | Project root the plugin auto-maps on session start (REQUIRED — never guessed) |
| `exclude_globs` | list | Glob patterns (POSIX, relative to active_project) to skip — vendor noise filter |

```bash
hermes config set plugins.entries.tricorder.active_project D:/Projects/projectm
hermes config set plugins.entries.tricorder.exclude_globs '["vendor/**","third_party/**"]' --force
```

**Cache validity:** The plugin uses a **stat-based content signature** (not an mtime TTL) to decide whether the cached map is still valid. The CLI's `--signature-only` flag computes a sha256 over `{path}:{size}:{mtime}` for every source file and prints 16 hex chars. The plugin shells to the CLI for this, compares the result to the `project_sig` stored in the meta JSON, and skips rebuild if they match. Changing `exclude_globs` changes the file set, which changes the signature, which triggers a rebuild — no explicit invalidation. No `cache_ttl_seconds` knob exists. The signature replaces all TTL logic.

### Installation

```bash
# Install (idempotent reinstall after plugin changes):
hermes plugins install "http://127.0.0.1:3001/projects/tricorder.git#plugins/tricorder" --force --enable

# Set the active project once:
hermes config set plugins.entries.tricorder.active_project D:/Projects/<repo>
```

## DSH Integration

For deepseek-harness (dsh), use the downstream skill at `skills/tricorder-dsh/SKILL.md`. The MCP server is registered as `tricorder` via `dsh-mcp-client`, exposing tools as `mcp__tricorder__tricorder_scan`, `mcp__tricorder__tricorder_detect`, `mcp__tricorder__tricorder_symbols`, `mcp__tricorder__tricorder_detail`, `mcp__tricorder__tricorder_query`.

Install:

```bash
# 1. pip-install tricorder (builds the `tricorder-mcp` console script)
pip install -e "D:/Projects/tricorder"

# 2. install this skill into dsh
mkdir -p ~/.dsh/skills/tricorder
cp "D:/Projects/tricorder/skills/tricorder-dsh/SKILL.md" ~/.dsh/skills/tricorder/SKILL.md
```

Configure `cordis.patch.yml`:

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

## License

MIT. This is based on the RepoMap design from the Aider project; lineage documented above.