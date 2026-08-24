# Tricorder — Code Intelligence Scanner (CLI + MCP Server)

Tricorder is a code-intelligence scanner in the spirit of the *Star Trek* tricorder: point it at a codebase and it reads only what matters. It scans for symbols, signatures, references, and cross-file call graphs, then generates a compact "map" of the repository — highlighting important files, definitions, and their relationships. It runs as a **command-line application**, an **MCP (Model Context Protocol) server**, and a **Hermes plugin**. All three surfaces share the same lean map policy: prioritize navigation value, skip obvious noise, and avoid dumping the whole tree.

It leverages **tree-sitter** for accurate code parsing and the **PageRank** algorithm to rank code elements by importance, so the most relevant information is always prioritized. On a large repo a full tricorder map typically costs ~1.5% of the tokens of reading every file — and with the `--pre-index` fast path that ratio gets dramatically better on huge trees.

## Status

**Release Candidate 1** — full rebrand of the maintained, bug-fixed RepoMapper fork. All upstream bugs resolved; test suite passes.

- **Test coverage:** 123 tests passing (`pytest tests/ -q`) — token counting, T0/T1 context, caching, MCP path handling, noise filter, mermaid-top, exclude-untagged, quiet mode, gitignore filtering, search, import tracking, ctags/rg pre-index probe, graph query DSL, CLI autodiscovery, cross-surface budget parity, token budget fields, per-language signature contract matrix.
- **Python 3.11+** compatible.
- **Fixed:** 8 critical upstream bugs (NameError, TypeError, cache path, duplicate definitions, dead variables, redundant checks, dedup edge cases, `relative_to` crash).
- **Language coverage:** 11 grammars with signature extraction + return types (Python, JS, TS, C, C++, Java, Go, Rust, Swift, C#, Ruby); 28 languages total via the tree-sitter-language-pack + tree-sitter-languages grammar sets (see [Supported Languages](#supported-languages)).
- **Cross-file call graph** with import resolution across files.
- **MCP server** with 5 tools: `tricorder_scan`, `tricorder_symbols`, `tricorder_detect`, `tricorder_detail`, `tricorder_query`.
- **Hermes lifecycle plugin** — auto-injects a turn-0 nav digest on session start, registers `/tricorder` slash commands.
- **DSH skill** — downstream port for the deepseek-harness MCP bridge.

## Table of Contents

- [Features](#features)
- [Installation](#installation)
- [CLI Usage](#cli-usage)
  - [Basic Usage](#basic-usage)
  - [Advanced Options](#advanced-options)
  - [Optimal Agent Workflow (Lowest Token Cost)](#optimal-agent-workflow-lowest-token-cost)
  - [Pre-Index Probe (rg / ctags) — fast path for huge repos](#pre-index-probe-rg--ctags--fast-path-for-huge-repos)
  - [Turn-0 Probe Digest](#turn-0-probe-digest)
- [How It Works](#how-it-works)
- [Output Format & Tiers](#output-format--tiers)
- [Dependency Graph (Mermaid)](#dependency-graph-mermaid)
- [Caching](#caching)
- [Supported Languages](#supported-languages)
- [Benchmarks](#benchmarks)
- [Running as an MCP Server](#running-as-an-mcp-server)
  - [MCP Setup](#mcp-setup)
  - [MCP Tools](#mcp-tools)
- [Hermes Lifecycle Plugin](#hermes-lifecycle-plugin)
- [DSH Integration](#dsh-integration)
- [Lineage & Attribution](#lineage--attribution)
- [License](#license)

## Features

- **Smart code analysis** — tree-sitter parsing for function/class/method/type definitions.
- **Relevance ranking** — PageRank over a file+symbol reference graph.
- **Token-aware** — respects token limits to fit LLM context windows.
- **Caching** — persistent on-disk cache for fast subsequent runs (content-aware invalidation via stat-based signatures).
- **Multi-language** — Python, JavaScript, TypeScript, Java, C/C++, Go, Rust, Ruby, C#, Swift, and more (tree-sitter grammars).
- **Important file detection** — prioritizes README, requirements.txt, etc.
- **Untagged files** — config/helpers/imports with no symbols shown separately.
- **Line counts** — each file header shows `(N lines)`.
- **Import tracking** — language-agnostic import parsing (Python, JS/TS, Java, C/C++, Go, Rust) with qualified-name resolution — disambiguates `Path()` vs `pathlib.Path()` across files.
- **C++ support** — full symbol extraction: signatures with params/return types, cross-file caller/callee via reference captures, `.h` parsed as C++ for class/method/namespace awareness.
- **Cross-file call graph** — callers/callees with import resolution across files.
- **Graph query DSL** — `callers('sym') depth=2 exclude=tests/**` — replaces 5+ round-trips for call-graph exploration.
- **Mermaid graph output** — dependency flowcharts with chat files highlighted.
- **Pre-index probe** — `--pre-index SYMBOL` narrows a huge tree (e.g. the Linux kernel) to matching files in ~1 second, no full-tree walk.

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
1. `--chat-files` — highest priority, assumed current work.
2. `--mentioned-files` — high priority, explicitly mentioned in context.
3. `--other-files` — lowest priority, additional context.

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

# Huge repo (e.g. the Linux kernel): narrow the scan to files containing a symbol
tricorder D:/Projects/linux --pre-index "pick_next_task" --pre-index-max-files 20 --map-tokens 2048
```

### Optimal Agent Workflow (Lowest Token Cost)

1. **Direct access** (0 map tokens): path known → read directly; symbol known → use `tricorder_detect`/grep. Don't run a full scan for a known symbol.
2. **Architecture / topography** (~1k–3k tokens): `tricorder . --mermaid` for module/component structure.
3. **Subsystem symbols (T0)** (~1k–2k tokens): `--tier 0` scoped to `src/sub/`. At ~14 tokens/tag, `--map-tokens 2048` ≈ 140 definitions.
4. **Targeted reading** (~100–500 tokens): `read_file` with the line numbers found. Direct read beats T1 for a single target.
5. **Huge-repo drill-in (pre-index)**: `--pre-index SYMBOL` narrows the scan to files containing that symbol — sub-second even on the Linux kernel. Use when scanning a giant tree for a known identifier.

### Pre-Index Probe (rg / ctags) — fast path for huge repos

For a known symbol in a large tree (kernel, monorepo), a full scan wastes time walking every file. The `--pre-index` probe narrows the file set *before* any scan:

```bash
tricorder D:/Projects/linux --pre-index "pick_next_task" --pre-index-max-files 20 --map-tokens 2048
```

- **rg-first:** `rg -l -w SYMBOL` with multi-language globs is the primary path — no index, no full-tree walk (a 6-file `kernel/sched/` narrow on the Linux kernel produces a full map in ~1.1s). Only file paths are read from rg, so Windows drive-letter colons can't corrupt the result.
- **ctags fallback:** used only if rg finds nothing. Index builds are **refused** on trees with >20,000 source files (env `TRICORDER_MAX_SCAN_FILES` defaults to 20,000), and any existing `tags` index larger than 100 MB is ignored as corrupt/stale — so a probe can never trigger a giant tree-walk or a multi-hundred-MB index build.
- `--pre-index-max-files N` (default 100): cap on files included from the probe.
- `--pre-index-include-parents N` (default 0): also include N parent directories of each matched file.

Pick a **specific** symbol for the probe — a common word (e.g. `schedule`, thousands of matches) caps out the file set and lands on the wrong files. A distinctive one (`pick_next_task`, ~6 matches in `kernel/sched/`) lands exactly on the relevant subtree.

When `--pre-index` is given, the probe runs **before** any path-walk and is authoritative (path-only walks are skipped entirely). If it finds nothing, tricorder falls back to the normal auto-scan. The same `pre_index`/`pre_index_max_files`/`pre_index_include_parents` args are available on the MCP `tricorder_scan` tool and the plugin.

### Turn-0 Probe Digest

```bash
tricorder --root D:/Projects/linux --probe-digest
```

Prints a cheap **navigation digest** — language tally + total code files + rough line estimate + a pointer to the MCP tools — and exits. It runs a fast `os.walk`-based extension tally (milliseconds, even on the Linux kernel) and **never builds a map or computes a token budget**. This is the exact text the Hermes and DSH plugins inject at turn 0 (single shared code path: `utils.probe_project` + `utils.format_probe_digest`). Repos with fewer than 200 code files print nothing.

## How It Works

1. **File discovery** — scans source files, skipping `.gitignore`d dirs (plus `build/`, `dist/`, `node_modules/`, `__pycache__/`, etc.). Discovery **early-stops** after 20,000 files (`TRICORDER_MAX_SCAN_FILES`) so a giant tree is never fully enumerated; a `--pre-index SYMBOL` probe runs first and skips the tree-walk entirely (see [Pre-Index Probe](#pre-index-probe-rg--ctags--fast-path-for-huge-repos)).
2. **Code parsing** — tree-sitter extracts definitions/references.
3. **Graph building** — files = nodes, symbol references = edges.
4. **Ranking** — PageRank over the graph.
5. **Token optimization** — binary search fits the most important content within token limits.
6. **Output generation** — readable code map.

This same discovery policy is shared by the CLI, MCP server, and Hermes plugin, so a repo that looks lean in one surface looks lean in the others too.

## Output Format & Tiers

- **T0 (default):** definition lines only — minimal tokens, find targets fast.
- **T1:** definitions + N lines of surrounding context — verify relevance without loading full files.

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

- Cache directory: `.tricorder.tags.cache.v1/` (in the scanned project's root).
- Auto-invalidated when files change via content-aware signatures (sha256 of path+size+mtime per source file); cleared with `--force-refresh`.
- **Gotcha:** after installing new tree-sitter parsers, maps may be empty from a stale cache — use `--force-refresh` or delete the cache dir.
- `--signature-only` prints the 16-char content signature for debugging cache validity.

## Supported Languages

Tricorder parses any tree-sitter-supported grammar. Two query packs are shipped under `queries/`:

- **`tree-sitter-language-pack`** (29 grammars): arduino, c, chatito, commonlisp, cpp, csharp, d, dart, elisp, elixir, elm, gleam, go, hcl, java, javascript, lua, ocaml, ocaml_interface, pony, properties, python, r, racket, ruby, rust, solidity, swift, udev.
- **`tree-sitter-languages`** (22 grammars, adds): kotlin, php, ql, scala, typescript (plus re-confirms c, cpp, elixir, elm, go, hcl, java, javascript, ocaml, ruby, rust).

**Union = 28 distinct languages.** The canonical language list is the extension map in `utils.py` (`EXTENSIONS` around line 272); `detect_lang()` resolves each source file to one of the grammar keys above. `.h` files are mapped to `cpp` (the cpp grammar is a strict superset of C — see the `ponytail:` note in `utils.detect_lang`).

**Signature extraction + return types (11 grammars):** Python, JavaScript, TypeScript, C, C++, Java, Go, Rust, Swift, C#, Ruby. Each of these 11 produces at least one definition symbol with a non-empty signature (parameters + return type where the grammar exposes one). This is enforced by `tests/test_language_matrix.py` (`test_claimed_languages_extract_defined_signature`): a failing grammar/query breaks the test. The wider 28-language pack is separately asserted to extract at least a definition symbol (`test_wider_language_pack_extracts_definitions`).

## Benchmarks

Tricorder's whole point is token savings: a compact map steers an agent to the right code without reading the entire repo. The efficacy is measured with `bench/bench_validity.py` (CLI surface) and `bench/bench_validity_mcp.py` (MCP surface). Each task poses a realistic agent question; `ground_truth` identifiers must appear in the map for a PASS.

| Repo | Tasks | Suite | Map Tokens | Full Repo | Savings |
|------|-------|-------|------------|-----------|---------|
|| projectm | 2/2 | bench_validity.py | 2,048 | 642,428 | 99.7% |
|| projectm | 2/2 | bench_validity_mcp.py | (221 + 1,358) | 642,428 | 100.0% + 99.8% (MCP) |
|| vaultwarden | 2/2 | bench_validity.py | 32,563 | 755,518 | 95.7% |
|| vaultwarden | 2/2 | bench_validity_mcp.py | (1,173 + 2,695) | 755,518 | 99.8% + 99.6% (MCP) |
|| linux | 1/1 | bench_validity.py | 39,936 | 50,352,437 | 99.9% |
|| linux | 1/1 | bench_validity_mcp.py | 5,500 | 50,352,437 | 100.0% (MCP, pre-indexed) |

**RESULT: ALL TASKS PASS.**

- **projectm** (~5,800 files, ~1.1M lines, C++): ~100% token savings; 2K-token map covers `PCM::AddToBuffer`, `Loudness`, `CurrentRelative`, `AverageRelative`.
- **vaultwarden** (~200 Rust files): ~96–99.8% token savings; 33K-token map covers `generate_invite`, `delete_user`, `admin_page`, `hash_password`, `verify_password_hash`, `routes`, `catchers`.
- **linux** (Linux kernel, ~50M tokens full): the headline case. With `--pre-index pick_next_task` the map narrows to `kernel/sched/` and ships in **~1.1s** (no full-tree walk, no ctags index), covering `pick_next_task`, `schedule`, `update_curr` at 99.9% savings over the full 50M-token tree. Use a *specific* probe symbol: common words across the kernel cap out at 100 files and miss the target.

**Note on the linux slot (both suites):** the `--pre-index pick_next_task` probe (CLI) and the `pre_index="pick_next_task"` param on `tricorder_detect` (MCP) narrow the 66k-file kernel tree to `kernel/sched/*` (~6 files). Without scoping, MCP detect walks all 66k files per query and is cold-cache-flaky (a first run can transiently miss a deep-callgraph symbol like `update_curr`). With scoping it is deterministic — verified 3x consecutive PASS on both surfaces, identical token figures.

**MCP token shape differs from CLI:** `bench_validity_mcp.py` exercises `tricorder_detect` (per-file definition records), not a serialized map — so MCP "tokens" scale with *result count* per identifier, not with a map blob. projectm MCP tokens are therefore an order of magnitude smaller than its CLI map (1358 vs 2048); vaultwarden's grow to ~2695 because `schedule`-class symbols match more definition sites. Savings are measured against the same full-repo estimate in both suites.

Both CLI and MCP surfaces are effective; savings scale with repo size.

**MCP `tricorder_detect` now supports `pre_index`** (mirrors CLI's `--pre-index` family: `pre_index`, `pre_index_max_files`, `pre_index_include_parents`) so per-symbol searches on huge repos (e.g. the Linux kernel) can be scoped to files containing a probe symbol instead of walking every file. The linux MCP slot uses `pre_index="pick_next_task"` to narrow to `kernel/sched/*` — runtime dropped from ~168s (full-tree walk) to ~64s, and it is no longer cold-cache-flaky.

### Pre-requisites (system-level)

Tricorder is a Python package; its runtime deps are pip-installed into a venv. These **external system tools** must be on `PATH`:

| Tool | Required? | Used for |
|------|-----------|----------|
| `python` (3.11+) | yes | running tricorder, MCP server, tests, bench |
| `git` | yes | `.gitignore` honoring + `.git` root auto-discovery |
| `rg` (ripgrep) | optional | the `--pre-index` probe / `pre_index` MCP param (fast path for huge trees). If absent, tricorder falls back to a full tree walk — the linux MCP slot works but is slower (no probe scoping). |
| `ctags` (UniversalCtags) | optional | fallback index for `tricorder_detect` when `rg` is absent and `rg`-based probe hits its 100-file ceiling. Rare on this codebase (rg is the primary path). |
| `tree-sitter` (CLI) | **not required** | only for building *custom* grammar repos from source. The vendored query sets under `queries/tree-sitter-language-pack/` and `queries/tree-sitter-languages/` ship as `.scm` files; Python tree-sitter bindings are pip-installed at run time. |

Verify with: `python bench/bench_validity.py --check-env` (prints presence/absence of rg, ctags, git, tree-sitter).

### How to reproduce

- **Repos:** [projectm](https://github.com/projectM-team/projectm) (libprojectM, C++), [vaultwarden](https://github.com/dani-garcia/vaultwarden) (Rust), and a Linux kernel checkout. Place them under one parent dir (default `D:\Projects` → `D:\Projects\projectm`, `D:\Projects\vaultwarden`, `D:\Projects\linux`).
- **Run:**
  ```bash
  # from the tricorder repo root, in its venv
  python bench/bench_validity.py               # CLI surface (all repos, incl. linux)
  python bench/bench_validity_mcp.py           # MCP surface
  python bench/bench_validity.py linux         # linux fast-path slot only (CLI surface)
  python bench/bench_validity_mcp.py            # MCP surface (projectm + vaultwarden + linux)
  # point at your own checkouts:
  python bench/bench_validity.py --root /path/to/your/repos
  ```
  Note: `rg` must be on `PATH` for the `--pre-index` fast path (used by the linux slot) — if the probe falls back to a full discovery and the map covers ~1% of files, that's the symptom.
- **Task definitions:** live in `bench/bench_validity*.py` (`REPOS` list — realistic agent questions + `ground_truth` identifiers).
- No CI benchmark machinery — run locally to re-verify; numbers are reproducible within noise on the same public repos.

## Running as an MCP Server

### MCP Setup

Tricorder runs as an MCP server over **STDIO**.

#### Hermes Agent (primary integration)

Register it under `mcp_servers:` in `~/.hermes/config.yaml`, then restart Hermes (no hot-reload — a restart is required). The 5 tools appear in every conversation as `mcp_tricorder_scan`, `mcp_tricorder_detect`, `mcp_tricorder_symbols`, `mcp_tricorder_detail`, `mcp_tricorder_query`.

```yaml
mcp_servers:
  tricorder:
    command: "C:/absolute/path/to/tricorder/.venv/Scripts/tricorder-mcp.exe"
    args: []
```

Requires the `mcp` Python package in the Hermes host (`pip install mcp`). A bundled skill (`skills/tricorder/SKILL.md`) teaches the agent the escalation ladder: T0 map → detect/symbols → detail → tier-1 scan → full-file read (last resort). No plugin code is required — native MCP client is the supported path.

#### Other clients (Cline/Roo)

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
| `tricorder_scan` | Generate a repository map for a project. Param `output_format` = `text` (prioritized definitions) or `mermaid` (dependency flowchart). Param `tier` = `0` (definitions only) or `1` (+ context). Also `token_limit`, `chat_files`, `other_files`, `mentioned_files`/`mentioned_idents`, `exclude_unranked`, `exclude_untagged`, `force_refresh`, `max_context_window`, `output_file`, `dry_run`, `exclude_globs` (list of glob patterns, e.g. `["vendor/**"]`, to drop third-party subtrees from the auto-scan before ranking), and `pre_index`/`pre_index_max_files`/`pre_index_include_parents` (narrow the scan to files containing a symbol — same as the CLI `--pre-index` family, for huge trees). Returns token budget fields: `token_estimate`, `full_repo_estimate`, `savings_pct`, `tier_hint`. |
|| `tricorder_detect` | Search for identifiers by name across the codebase. Case-insensitive; returns file, line, def/ref kind, context. Params `query`, `max_results`, `context_lines`, `include_definitions`, `include_references`, and `pre_index`/`pre_index_max_files`/`pre_index_include_parents` (scope the search to files containing a probe symbol — same as CLI `--pre-index`, for huge repos; the linux MCP bench uses `pre_index="pick_next_task"` to avoid a full-tree walk). |
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

The plugin (`plugins/tricorder/`) is a real Hermes plugin (manifest + `__init__.py` with `register(ctx)`) installed to `~/.hermes/plugins/tricorder/` via `hermes plugins install`. It wires the `on_session_start` + `pre_llm_call` hooks to inject a **turn-0 probe digest** into the first turn's user message — a cheap navigation item (language tally + file count + rough line estimate + a pointer to the MCP tools for depth). It **never builds the full repo map on turn 0** (on a kernel-scale tree that would block/timeout); maps are built on demand via `/tricorder scan` or the MCP tools. It also registers `/tricorder` slash commands and the `tricorder:tricorder` skill.

The digest text is produced by the shared CLI flag `--probe-digest` (single source of truth: `utils.probe_project` + `utils.format_probe_digest`), which the DSH plugin (`plugins/dsh-tricorder-inject`) calls too — so Hermes and DSH inject **byte-identical** turn-0 content. Repos with fewer than 200 code files get no digest.

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

There are two pieces for deepseek-harness (dsh):

1. **Turn-0 probe-digest injector** — `plugins/dsh-tricorder-inject/` (vendored Cordis plugin, `@deepseek-ai/dsh-tricorder-inject`). On session create it runs `tricorder --root <cwd> --probe-digest` and injects the **same** navigation digest Hermes injects (identical text, single shared code path). It never builds the full repo map on turn 0. Install by copying `plugins/dsh-tricorder-inject` into your dsh profile's `node_modules/@deepseek-ai/dsh-tricorder-inject` (or `pnpm add` from that path) and enabling it in `cordis.patch.yml`.
2. **MCP tools + skill** — the downstream skill at `skills/tricorder-dsh/SKILL.md`. The MCP server is registered as `tricorder` via `dsh-mcp-client`, exposing tools as `mcp__tricorder__tricorder_scan`, `mcp__tricorder__tricorder_detect`, `mcp__tricorder__tricorder_symbols`, `mcp__tricorder__tricorder_detail`, `mcp__tricorder__tricorder_query`.

Install:

```bash
# 1. pip-install tricorder (builds the `tricorder-mcp` console script)
pip install -e "D:/Projects/tricorder"

# 2. install this skill into dsh
mkdir -p ~/.dsh/skills/tricorder
cp "D:/Projects/tricorder/skills/tricorder-dsh/SKILL.md" ~/.dsh/skills/tricorder/SKILL.md

# 3. (optional) install the turn-0 probe-digest injector
mkdir -p "$HOME/.dsh/<profile>/node_modules/@deepseek-ai"
cp -r "D:/Projects/tricorder/plugins/dsh-tricorder-inject" "$HOME/.dsh/<profile>/node_modules/@deepseek-ai/dsh-tricorder-inject"
```

Configure `cordis.patch.yml`:

```yaml
- insert:
    - id: mcp-tricorder
      name: '@deepseek-ai/dsh-mcp-client'
      config:
        serverName: tricorder
        transport: stdio
        # Point command at YOUR tricorder-mcp console script. Find it with:
        #   pip show tricorder   # look for "Location", then <Location>/../Scripts/tricorder-mcp.exe  (Windows)
        #   which tricorder-mcp  # Linux/macOS
        command: <path-to-your-python>/Scripts/tricorder-mcp.exe   # Windows
        #        or <path-to-your-python>/bin/tricorder-mcp            # Linux/macOS
        args: []

    - id: tricorder-inject
      name: '@deepseek-ai/dsh-tricorder-inject'
      config:
        tricorderExe: 'D:/Projects/tricorder/.venv/Scripts/tricorder.exe'  # optional
        verbose: false
```

## Lineage & Attribution

Tricorder is a rebranded fork of the **RepoMapper** fork of **Aider's RepoMap**:

1. **Gen 1 — Aider `RepoMap`** (Paul Gauthier): tree-sitter symbol extraction + PageRank ranking.
2. **Gen 2 — RepoMapper** (Paul Davis `/ pdavis68`): standalone CLI + MCP server, built with Aider + Claude 3.7 + Cline + Gemini 2.5 Pro. Upstream: https://github.com/pdavis68/RepoMapper
3. **Gen 3 — tricorder**: our fork — 8 bug fixes, 123 tests, 10-language signature extraction, cross-file call graph, ctags/rg pre-index probe for huge repos, Windows compatibility, full rebrand to tricorder.

Lineage is intentionally kept visible. MIT Licensed.

## License

MIT. This is based on the RepoMap design from the Aider project; lineage documented above.