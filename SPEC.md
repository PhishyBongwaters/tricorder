# tricorder

**Star Trek-inspired code intelligence MCP server + Hermes plugin.**

tricorder scans codebases the way a Starfleet tricorder scans a planet: it senses, analyzes, and reports what's there — symbols, call graphs, signatures, references — without reading every file. You point it at a codebase; it tells you what matters.

Built on tree-sitter for parsing and PageRank for ranking, tricorder generates compressed maps that let humans and LLMs understand unfamiliar codebases at a fraction of the context cost.

---

## Origin Story

tricorder has a lineage worth telling.

### Generation 1: Aider

Paul Gauthier created [Aider](https://github.com/paul-gauthier/aider), an AI pair programmer. Aider includes a `RepoMap` class that uses tree-sitter to extract code symbols and PageRank to rank them by importance, producing a compressed "map" of a repository. This lets the LLM understand the codebase structure without reading every file — a fraction of the tokens, a fraction of the cost.

### Generation 2: RepoMapper

[Paul Davis (pdavis68)](https://github.com/pdavis68) reimplemented Aider's RepoMap from specifications, removed the Aider-specific dependencies, and made it a standalone CLI tool plus MCP server. He used a combination of Aider (with Claude 3.7), Cline (with Gemini 2.5 Pro), and various other LLM tools to build it. The result was RepoMapper — a general-purpose repo mapping tool that any MCP-compatible client could use.

Repo: https://github.com/pdavis68/RepoMapper

### Generation 3: The Fork

We forked RepoMapper and went deep on language coverage, correctness, and code intelligence:

- **8 critical bug fixes** — NameError, TypeError, cache path, duplicate definitions, dead variables, redundant checks, dedup edge cases, relative_to crash
- **73 tests** — zero existed in the original
- **10-language signature extraction** with return types — Python, JS/TS, C, C++, Java, Go, Rust, Swift, C#, Ruby
- **Cross-file call graph** — callers/callees with import resolution across files
- **Reference captures** — C `call_expression`/type refs, Swift `call_expression`/`navigation_expression`/`user_type` refs
- **Windows path normalization** — cross-file caller/callee false positives fixed (path separator mismatch)
- **`.h` → C++ mapping** — `grep_ast` mapped `.h` to C; overridden to map to C++
- **Mermaid graph output** with zero-tag file filtering
- **Tier system** (T0 definitions, T1 context) with token-aware escalation
- **MCP server** with 4 tools: `tricorder_scan`, `tricorder_symbols`, `tricorder_detect`, `tricorder_detail`

### Generation 4: tricorder

This is the rebrand. RepoMapper worked, but it was a fork that had outgrown its name. tricorder is the same code, repackaged as a first-class code-intelligence tool with:

- **Native MCP server** — register `tricorder-mcp` under `mcp_servers:` in Hermes `config.yaml`; its 4 tools then appear as `mcp_tricorder_*` in every conversation. This is the reliable on-demand tool surface.
- **Lifecycle plugin** — `plugins/tricorder/` binds `on_session_start` + `pre_llm_call` so the active project's T0 map is built and injected on the first turn automatically ("control, not assume"). Plus `/tricorder` slash commands.
- **Bundled skill** — `skills/tricorder/SKILL.md` teaches the agent the escalation ladder: T0 map → detect/symbols → detail → tier-1 scan → full-file read (last resort).

Both integrations delegate to the tricorder venv's own binaries (never imported in-process).
The MCP server covers on-demand probes; the plugin covers proactive mapping. Together they are
the "plugin" that makes tricorder a first-class Hermes citizen.

The name comes from the Star Trek tricorder — a handheld sensor device that scans, analyzes, and reports on unfamiliar environments. That's exactly what this tool does with codebases. 🖖

---

## Architecture

```
tricorder/
├── pyproject.toml              # tricorder package; entry points tricorder + tricorder-mcp
├── tricorder_server.py         # MCP server (FastMCP 'tricorder') — 4 tools
├── tricorder.py                # CLI entry point
├── core.py                     # Core: Tricorder class (parsing, ranking, call graph)
├── utils.py                    # Shared utilities (detect_lang, etc.)
├── name_resolver.py            # Cross-file import resolution
├── import_parser.py            # Language-specific import parsing
├── importance.py               # PageRank / importance ranking
├── scm.py                      # Git-aware file discovery + gitignore
├── queries/
│   └── tree-sitter-language-pack/
│       ├── python-tags.scm
│       ├── javascript-tags.scm
│       ├── c-tags.scm
│       ├── cpp-tags.scm
│       ├── csharp-tags.scm
│       ├── ruby-tags.scm
│       ├── swift-tags.scm
│       └── ... (20+ languages via tree-sitter-language-pack)
├── skills/
│   └── tricorder/              # bundled usage skill (SKILL.md)
├── plugins/
│   └── tricorder/              # Hermes lifecycle plugin (hooks + /tricorder slash cmd)
├── tests/                      # 75 tests (ported from RepoMapper fork)
├── README.md
├── SPEC.md
├── LICENSE                     # MIT
├── requirements.txt
```

### Integration reality

tricorder is a **real `plugin.yaml`-manifest plugin** (`plugins/tricorder/`) installed to
`~/.hermes/plugins/tricorder/` via `hermes plugins install`. It uses the standard Hermes
plugin surface: a plugin manifest + `__init__.py` with `register(ctx)` calling
`ctx.register_hook(...)` / `ctx.register_command(...)` / `ctx.register_skill(...)`. The
verified, working surfaces are:

- **Native MCP client (primary, required):** Hermes launches `tricorder-mcp.exe` (from the
  tricorder venv) via `config.yaml` → `mcp_servers:` and exposes the 4 tools as
  `mcp_tricorder_scan`, `mcp_tricorder_detect`, `mcp_tricorder_symbols`,
  `mcp_tricorder_detail`. Confirmed against the real Hermes host (v0.20.0). Requires the
  `mcp` Python package in the host and a Hermes restart after config change (no hot-reload).
  The tricorder venv (`D:/Projects/tricorder/.venv`, Python 3.11) already has `mcp`+`fastmcp`.
- **Lifecycle plugin (primary proactive surface) — BUILT:** `plugins/tricorder/` is a
  real Hermes plugin (manifest + `__init__.py` with `register(ctx)`). It wires the
  `on_session_start` + `pre_llm_call` hooks so the active project's T0 map is built once
  and a compact digest is injected into the first turn's user message — the agent gets
  the codebase skeleton *before* it acts. It also registers `/tricorder` slash commands
  (`root`, `scan`, `status`) and the `tricorder:tricorder` skill. See
  [Lifecycle Hooks](#lifecycle-hooks-real--this-is-the-control-not-assume-surface).
  Installed via `hermes plugins install <git>#plugins/tricorder --enable`.
- **Cross-venv note:** Hermes runs from `AppData\Local\hermes\hermes-agent\venv`; tricorder
  runs from its own venv (`D:/Projects/tricorder/.venv`, Python 3.11). The plugin never
  imports tricorder in-process — it shells to `tricorder.exe` once per project (on session
  start / stale first turn) and caches the map to `~/.hermes/tricorder/`. Per-turn hook
  calls read the disk cache, so there is no per-turn subprocess cost.
```

---

## MCP Tools (5)

### `tricorder_scan` (was `repo_map`)
Generate a ranked code map for a project directory. Writes to `output_file` to avoid context bloat.

```json
{
  "project_root": "/absolute/path/to/project",
  "token_limit": 2048,
  "tier": 0,
  "output_file": "/path/to/map.txt",
  "output_format": "text|mermaid",
  "chat_files": ["file.py"],
  "exclude_untagged": false
}
```

Returns the full map inline (`{"map": ...}`) by default. If `output_file` is set, returns `{"map_file": path, "token_estimate": N}` instead to avoid context bloat on large repos.

### `tricorder_symbols` (was `search_symbols`)
Structured symbol search with type and file filters. Returns full `SymbolRecord` data.

```json
{
  "project_root": "/absolute/path/to/project",
  "query": "auth",
  "type": "function|class|method|variable|import",
  "file": "auth.py",
  "limit": 50
}
```

### `tricorder_detect` (was `search_identifiers`)
Case-insensitive identifier search across all source files.

```json
{
  "project_root": "/absolute/path/to/project",
  "query": "main",
  "max_results": 50,
  "context_lines": 2,
  "include_definitions": true,
  "include_references": true
}
```

### `tricorder_detail` (was `get_symbol_details`)
Full details for a symbol: body, signature, docstring, callers, callees.

```json
{
  "project_root": "/absolute/path/to/project",
  "file": "auth.py",
  "name": "authenticate",
  "line": 42
}
```

Returns callers (in-file + cross-file with import resolution) and callees.

---

### `tricorder_query` (NEW — M0.10)
Execute graph traversal queries on the codebase call graph. Replaces 5+ round-trips for common agent graph traversals.

**DSL Grammar**:
```
query := traversal ('|' traversal)*
traversal := kind '(' target ')' modifiers?
kind := "callers" | "callees" | "refs" | "defs"
target := quoted string
modifiers := (modifier)*
modifier := "depth=" INT | "exclude=" GLOB | "include=" GLOB
          | "type=" ("function"|"class"|"method"|"variable") | "limit=" INT
```

```json
{
  "project_root": "/absolute/path/to/project",
  "query": "callers('authenticate') depth=2 exclude=tests/**",
  "token_limit": 2048
}
```

**Examples**:
- `callers('authenticate') depth=2` — all callers up to 2 hops
- `callees('main') depth=1 exclude=tests/**` — direct callees, skip tests
- `refs('Config') type=class limit=50` — all references to class Config
- `callers('foo') | callees('bar') depth=3` — chained traversals

**Returns**: `{nodes: [...], edges: [...], token_estimate, full_repo_estimate, savings_pct, tier_hint?, stats: {nodes_visited, edges_traversed}}`

- `nodes`: list of `{name, file, line, type}`
- `edges`: list of `{from, to, from_file, to_file, from_line, to_line, type}` where type is `calls`, `called_by`, `refers`, or `defines`
- Cross-file edges have different `from_file` / `to_file`
- `tier_hint` present if response truncated by `token_limit`

---

## Language Coverage

| Language | Refs | Sigs | Return Types | Notes |
|----------|------|------|-------------|-------|
| Python | ✓ | ✓ | ✓ | |
| JS/TS | ✓ | ✓ | ✓ | |
| C | ✓ | ✓ | ✓ | Reference captures: call_expression, type refs |
| C++ | ✓ | ✓ | ✓ | `.h` files map to C++ (not C) |
| Java | ✓ | ✓ | ✓ | Uses `formal_parameters` (not `parameter_list`) |
| Go | ✓ | ✓ | ✓ | |
| Rust | ✓ | ✓ | ✓ | `trailing_return_type` double-arrow fix |
| Swift | ✓ | ✓ | ✓ | Subtree walk for params (no list wrapper) |
| C# | ✓ | ✓ | ✓ | `predefined_type` + `identifier` return types |
| Ruby | ✓ | ✓ | ✓ | `method_parameters` param node |

---

## Slash Commands (built in the plugin)

The lifecycle plugin registers a single `/tricorder` slash command with subcommands.
The map itself is auto-injected via `pre_llm_call`; the slash command is for on-demand
control and project setup:

| Command | Description |
|---------|-------------|
| `/tricorder root <path>` | Set the active project (persists to `plugins.entries.tricorder.active_project`). Checks cache: if valid, reports "cache ready." If stale/missing, auto-rebuilds. |
| `/tricorder scan [path]` | Force-rebuild a repo map (default: active project). Ignores signature. |
| `/tricorder status` | Show active project + cache state (valid/stale/missing, age) + all other cached projects. |

Symbol search/detail are **not** slash commands — they're the MCP tools
(`mcp_tricorder_detect/symbols/detail`), which already work and are better suited to
that (structured results, filters). The CLI only generates maps, so the plugin shells
to `tricorder.exe` for map production only; targeted probes route to MCP.

### Plugin config

Both knobs live under `plugins.entries.tricorder.*` in `~/.hermes/config.yaml`:

| Key | Type | Description |
|-----|------|-------------|
| `active_project` | string | Project root the plugin auto-maps on session start (REQUIRED — never guessed) |
| `exclude_globs` | list | Glob patterns (POSIX, relative to active_project) to skip — vendor noise filter |

```bash
hermes config set plugins.entries.tricorder.active_project D:/Projects/projectm
hermes config set plugins.entries.tricorder.exclude_globs '["vendor/**","third_party/**"]' --force
```

The CLI also exposes `--exclude-globs PATTERNS...` directly for ad-hoc runs (see SKILL.md).

**Cache validity:** The plugin uses a **stat-based content signature** (not an
mtime TTL) to decide whether the cached map is still valid. The CLI's
`--signature-only` flag computes a sha256 over `{path}:{size}:{mtime}` for every
source file and prints 16 hex chars. The plugin shells to the CLI for this,
compares the result to the `project_sig` stored in the meta JSON, and skips
rebuild if they match. Changing `exclude_globs` changes the file set, which
changes the signature, which triggers a rebuild — no explicit invalidation.

No `cache_ttl_seconds` knob exists. The signature replaces all TTL logic.

---

## Lifecycle Hooks (REAL — this is the "control, not assume" surface)

The plugin wires into Hermes' lifecycle hooks, which the live `VALID_HOOKS` set in
`hermes_cli/plugins.py` confirms **do exist** (the earlier "NOT available" claim was
stale). The relevant ones:

- **`on_session_start`** — fired once per new session (`agent/conversation_loop.py`).
  Checks the stat-based signature against the cached map. If valid → skip
  rebuild (files unchanged). If stale/missing → rebuild. This is the
  "project opened → map it (if it changed)" trigger.
- **`pre_llm_call`** — fired before each LLM call (`agent/turn_context.py`). A plugin
  may return `{"context": "..."}` (or a plain string) which Hermes **injects into the
  current turn's user message** — ephemeral, never persisted, system prompt stays
  byte-stable (prompt-cache friendly). On the first turn: if the signature matches
  the cache, inject from disk (no rebuild). If stale/missing, rebuild + inject.
  Later turns: silent.

Also available (not used yet): `post_llm_call`, `pre_tool_call`, `post_tool_call`,
`pre_verify`, `on_skill_lifecycle`, `subagent_start`/`stop`, kanban + approval hooks,
`on_session_end`.

**Active project is declared, never assumed.** Both hooks receive `session_id`,
`model`, `platform` — but **no cwd/project root**. So the plugin reads the active
project from config: `plugins.entries.tricorder.active_project` (via `/tricorder root
<path>` or `hermes config set`). It does not sniff paths from messages or cwd.

**Bounded, not chatty.** The map is built once (on session start / stale first turn);
the digest is injected only on the first turn. Later turns stay silent — the map file
+ MCP tools + skill cover follow-up access, keeping context economy intact (~1.5% of
full-repo cost).

---

## Token Economy

The entire point of tricorder is context efficiency. An LLM agent understanding a codebase has two options:

1. **Read every file** — 32,620 tokens for a medium repo
2. **Use tricorder** — 491 tokens for the same repo (1.5% of full)

| Approach | Chars | Tokens |
|----------|-------|--------|
| Full repo scan | 133,432 | 32,620 |
| tricorder T0 map | 1,702 | 491 |
| **Savings** | **131,730** | **32,129 (98.5%)** |

### Tier system

- **Mermaid** — dependency graph (module relationships only). Cheapest.
- **T0** — definitions only (~14 tokens/tag). Locate a symbol.
- **T1** — definitions + context lines (~350 tokens/tag). Assess relevance.

Stop at the first tier that answers the question.

---

## Cache Sharing

| Component | Cache Role |
|-----------|------------|
| `tricorder` (CLI) | **Writer** — builds `TAGS_CACHE`, import index, call graph |
| `tricorder-mcp` | **Reader** — queries cache via `Tricorder` methods (MCP tools) |

The `diskcache` backend handles concurrent readers + single writer safely.

---

## License

MIT — same as Aider and RepoMapper. Fully open source.

---

## Attribution

tricorder builds on the work of:

1. **Paul Gauthier** — [Aider](https://github.com/paul-gauthier/aider) — the original RepoMap concept and implementation using tree-sitter + PageRank.

2. **Paul Davis (pdavis68)** — [RepoMapper](https://github.com/pdavis68/RepoMapper) — reimplemented Aider's RepoMap as a standalone CLI + MCP server, using LLMs to generate specs from Aider's code and then build from those specs.

3. **The Hermes Agent community** — for the plugin system, MCP client, and tool framework that tricorder plugs into.

The code in this repository is a rebrand and repackaging (as an MCP server + bundled skill,
with optional slash-command plugin) of the RepoMapper fork maintained at `http://127.0.0.1:3001/projects/repomapper.git`. The fork added 8 bug fixes, 73 tests, 10-language coverage, cross-file call graph analysis, and Windows compatibility — all of which carry forward to tricorder.

---

## Status

**Phase 1 (rebrand) complete** — RepoMapper fork imported and fully rebranded to tricorder
(see git log). 73 tests green (now 75, incl. `exclude_globs`); CLI and MCP server verified.
**Phase 2 (Hermes integration) complete** — bundled skill (`skills/tricorder/`) added and
installed; the MCP server is registered under Hermes' `mcp_servers:` (command points at the
venv's `tricorder-mcp.exe`) and the `mcp` client SDK is present, so after a Hermes restart the
4 tools appear as `mcp_tricorder_scan/detect/symbols/detail`. SPEC.md documents design
and the *real* integration surface — where the design is not yet supported by Hermes, that
is flagged explicitly rather than assumed.
**Phase 3 (lifecycle plugin) complete** — `plugins/tricorder/` built and installed to
`~/.hermes/plugins/tricorder`, enabled in config. `on_session_start` builds the active
project's T0 map; `pre_llm_call` injects a bounded digest on the first turn (verified 1/0
injection on first/later turns through the real singleton `invoke_hook` pipeline);
`/tricorder root|scan|status` slash commands registered; `tricorder:tricorder` skill
registered. This is the "control, not assume" surface: the agent gets the codebase skeleton
fed to it without having to choose to scan. **This makes tricorder a release candidate.**

```
# Install (idempotent reinstall after plugin changes):
hermes plugins install "http://127.0.0.1:3001/projects/tricorder.git#plugins/tricorder" --force --enable
# Set the active project once:
hermes config set plugins.entries.tricorder.active_project D:/Projects/<repo>
```
