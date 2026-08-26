# Tricorder — Code Intelligence Scanner (CLI + MCP Server)

## Executive Summary

Tricorder transforms incomprehensible codebases into actionable intelligence. Instead of drowning in 50M tokens of Linux kernel, you get a 40K-token map with **99.9% token savings** — pointing you straight to `kernel/sched/fair.c:pick_next_task` in ~1.1s.

## Why Tricorder Matters

| Traditional Approach | Tricorder Approach |
|---|---|
| ❌ Read every file (hours) | ✅ Intelligent mapping (seconds) |
| ❌ Hit-or-miss search | ✅ Precise symbol detection |
| ❌ Manual dependency tracing | ✅ Auto call-graph + PageRank |
| ❌ Context window overflow | ✅ Token-aware exploration |

**Real impact:** 15/15 benchmarks pass across C++, Rust, TypeScript, Go, Linux kernel.

## Three Integrated Interfaces

```
CLI ──► tricorder .                    # Human/agent direct use
MCP ──► tricorder-mcp (STDIO)          # Any MCP client (Hermes, Cline, etc.)
Hermes/DSH ──► plugins + turn-0 digest # Auto-inject nav digest at session start
```

## Smart Escalation Ladder (stop at first rung that answers your question)

```
1️⃣ T0 MAP (~14 tokens/tag)   → "Database classes in database.py"
2️⃣ DETECT (~1-2 tokens/tag)  → "Found getConnection() at database.py:42"
3️⃣ DETAIL (~50-400 tokens)   → Full function + callers
4️⃣ T1 SCAN (~350 tokens/tag) → 3 lines context around function
5️⃣ FULL FILE (last resort)   → Read entire file when necessary
```

## Quick Start

```bash
python -m venv .venv && .venv/Scripts/pip install -r requirements.txt
tricorder .                          # Map current dir
tricorder . --mermaid --top 10       # Dependency graph
```

## Core Features

- **Tree-sitter + PageRank** — accurate parsing, relevance-ranked maps
- **Token-aware** — binary search fits map to budget (~1.5% of full repo)
- **Pre-index probe** — `--pre-index SYMBOL` narrows huge trees in ~1s (rg-first, no full walk)
- **Graph query DSL** — `callers('auth') depth=2 exclude=tests/**` replaces 5+ round-trips
- **Mermaid graphs** — dependency flowcharts with chat files highlighted
- **Cross-file call graph** — import-resolved callers/callees
- **Caching** — content-aware invalidation, outside repo (TC-003)
- **28 languages** — 11 with signatures+return types

## CLI Usage

### Basic Mapping

```bash
tricorder .                         # Map current directory
tricorder src/ --map-tokens 2048    # Specific directory with token limit
tricorder file1.py file2.py         # Specific files
tricorder --chat-files main.py --other-files src/  # Prioritized file sets
```

### File Priority Order

1. `--chat-files` — highest priority (current work)
2. `--mentioned-files` — high priority (explicitly mentioned)
3. `--other-files` — lowest priority (additional context)

### Advanced Options

```bash
tricorder . --verbose
tricorder . --force-refresh          # Bust cache
tricorder . --exclude-unranked       # Drop zero-score files
tricorder . --exclude-untagged       # Drop files with no symbols
tricorder . --quiet
tricorder . --dry-run --map-tokens 2048
tricorder . --max-files 5000         # Raise auto-discovery cap (default 1000)
tricorder . --exclude-globs vendor/** third_party/**
tricorder . --top 10                 # Top N ranked files
tricorder . --mermaid --mermaid-top 30  # Mermaid flowchart
tricorder . --signature-only         # Content signature for cache debugging
```

### Output Tiers

- **T0 (default):** definition lines only — ~14 tokens/tag, find targets fast
- **T1:** definitions + N lines context — verify relevance without loading full files

```bash
tricorder . --tier 0
tricorder . --tier 1 --context-lines 3
tricorder . --tier 1 --context-lines 5 --map-tokens 4096
```

### Optimal Agent Workflow (Lowest Token Cost)

1. **Direct access (0 tokens):** path known → read directly; symbol known → `tricorder_detect`/grep
2. **Architecture overview (~1K-3K tokens):** `tricorder . --mermaid` for module structure
3. **Subsystem symbols (~1K-2K tokens):** `--tier 0` scoped to `src/sub/`
4. **Targeted reading (~100-500 tokens):** `read_file` with line numbers from map
5. **Huge-repo drill-in (pre-index):** `--pre-index SYMBOL` for giant trees

### Pre-Index Probe — Fast Path for Huge Repos

For a known symbol in a large tree (kernel, monorepo), a full scan wastes time walking every file:

```bash
tricorder D:/Projects/linux --pre-index "pick_next_task" --pre-index-max-files 20 --map-tokens 2048
```

- **rg-first:** `rg -l -w SYMBOL` with multi-language globs — no index, no full-tree walk (6-file `kernel/sched/` narrow on Linux kernel = full map in ~1.1s)
- **ctags fallback:** only if rg finds nothing; index builds refused on >20,000 source files, >100MB tags ignored as corrupt
- `--pre-index-max-files N` (default 100): cap files from probe
- `--pre-index-include-parents N` (default 0): also include N parent dirs

Pick a **specific** symbol — `pick_next_task` (~6 matches) lands on `kernel/sched/`; `schedule` (thousands) caps out and misses.

When `--pre-index` is given, the probe runs **before** any path-walk and is authoritative. Same `pre_index`/`pre_index_max_files`/`pre_index_include_parents` args available on MCP `tricorder_scan` and plugin.

## MCP Server

Tricorder runs as an MCP server over **STDIO**.

### Hermes Agent (Primary Integration)

Register under `mcp_servers:` in `~/.hermes/config.yaml`, restart Hermes:

```yaml
mcp_servers:
  tricorder:
    command: "C:/absolute/path/to/tricorder/.venv/Scripts/tricorder-mcp.exe"
    args: []
```

Requires `mcp` Python package (`pip install mcp`). A bundled skill teaches the escalation ladder.

### Other Clients (Cline/Roo)

Add to `cline_mcp_settings.json`:

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

Or run directly: `python tricorder_server.py`

### MCP Tools

| Tool | Purpose |
|------|---------|
| `tricorder_scan` | Generate repo map. `output_format`: `text` or `mermaid`. `tier`: `0` or `1`. Also `token_limit`, `chat_files`, `other_files`, `mentioned_files/idents`, `exclude_unranked`, `exclude_untagged`, `force_refresh`, `max_context_window`, `output_file`, `dry_run`, `exclude_globs`, `pre_index`/`pre_index_max_files`/`pre_index_include_parents`. Returns `token_estimate`, `full_repo_estimate`, `savings_pct`, `tier_hint`. |
| `tricorder_detect` | Search identifiers by name. Case-insensitive; returns file, line, def/ref kind, context. Params: `query`, `max_results`, `context_lines`, `include_definitions`, `include_references`, `pre_index`/`pre_index_max_files`/`pre_index_include_parents`. |
| `tricorder_symbols` | Structured symbol query with type + file filters. Returns full records (name, type, file, line range, signature, docstring, language, ts-kind). Params: `query`, `type`, `file`, `limit` (default 50, cap 200). |
| `tricorder_detail` | Deep-dive on a symbol — body, callers, callees. Params: `name`, `file`, `line`. |
| `tricorder_query` | Graph traversal DSL: `callers('sym') depth=2 exclude=tests/** \| callees('other') type=class`. Returns `{nodes, edges, token_estimate, savings_pct}`. |

**Example `tricorder_scan` (mermaid):**
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

## Hermes Lifecycle Plugin

Plugin (`plugins/tricorder/`) installs to `~/.hermes/plugins/tricorder/` via `hermes plugins install`. Wires `on_session_start` + `pre_llm_call` to inject a **turn-0 probe digest** (language tally + file count + line estimate + MCP tool pointer) — **never builds full map on turn 0**. Also registers `/tricorder` slash commands.

### Slash Commands

| Command | Description |
|---------|-------------|
| `/tricorder root <path>` | Set active project (persists). Checks cache: valid → "cache ready"; stale/missing → auto-rebuild. |
| `/tricorder scan [path]` | Force-rebuild repo map (default: active project). Ignores signature. |
| `/tricorder status` | Show active project + cache state (valid/stale/missing, age) + all cached projects. |

### Plugin Config

Under `plugins.entries.tricorder.*` in `~/.hermes/config.yaml`:

| Key | Type | Description |
|-----|------|-------------|
| `active_project` | string | **Required** — project root to auto-map on session start |
| `exclude_globs` | list | Glob patterns (POSIX, relative to active_project) to skip |

```bash
hermes config set plugins.entries.tricorder.active_project D:/Projects/projectm
hermes config set plugins.entries.tricorder.exclude_globs '[\"vendor/**\",\"third_party/**\"]' --force
```

**Cache validity:** Stat-based content signature (not TTL). CLI `--signature-only` computes sha256 over `{path}:{size}:{mtime}` per source file; plugin shells to CLI, compares to stored `project_sig`. Changing `exclude_globs` changes file set → signature changes → rebuild triggered.

### Installation

```bash
hermes plugins install "http://127.0.0.1:3001/projects/tricorder.git#plugins/tricorder" --force --enable
hermes config set plugins.entries.tricorder.active_project D:/Projects/<repo>
```

## DSH Integration

Two pieces for deepseek-harness:

1. **Turn-0 probe-digest injector** — `plugins/dsh-tricorder-inject/` (vendored Cordis plugin). Runs `tricorder --root <cwd> --probe-digest`, injects same digest as Hermes. Install by copying into dsh profile's `node_modules/@deepseek-ai/dsh-tricorder-inject` and enabling in `cordis.patch.yml`.

2. **MCP tools + skill** — downstream skill at `skills/tricorder-dsh/SKILL.md`. MCP server registered as `tricorder` via `dsh-mcp-client`.

```bash
pip install -e "D:/Projects/tricorder"
mkdir -p ~/.dsh/skills/tricorder
cp "D:/Projects/tricorder/skills/tricorder-dsh/SKILL.md" ~/.dsh/skills/tricorder/SKILL.md
```

`cordis.patch.yml`:
```yaml
- insert:
    - id: mcp-tricorder
      name: '@deepseek-ai/dsh-mcp-client'
      config:
        serverName: tricorder
        transport: stdio
        command: <path-to-python>/Scripts/tricorder-mcp.exe
        args: []

    - id: tricorder-inject
      name: '@deepseek-ai/dsh-tricorder-inject'
      config:
        tricorderExe: 'D:/Projects/tricorder/.venv/Scripts/tricorder.exe'
        verbose: false
```

## Benchmarks

Tricorder's whole point is token savings: a compact map steers an agent to the right code without reading the entire repo. Efficacy measured with `bench/bench_validity.py` (CLI) and `bench/bench_validity_mcp.py` (MCP). Each task poses a realistic agent question; `ground_truth` identifiers must appear in the map for a PASS.

| Repo | Tasks | Suite | Map Tokens | Full Repo | Savings |
|------|-------|-------|------------|-----------|---------|
| projectm | 2/2 | bench_validity.py | 2,048 | 642,428 | 99.7% |
| projectm | 2/2 | bench_validity_mcp.py | 221 / 1,358 | 642,428 | 100.0% / 99.8% |
| vaultwarden | 2/2 | bench_validity.py | 32,563 | 755,518 | 95.7% |
| vaultwarden | 2/2 | bench_validity_mcp.py | 1,173 / 2,695 | 755,518 | 99.8% / 99.6% |
| linux | 1/1 | bench_validity.py | 39,936 | 50,352,437 | 99.9% |
| linux | 1/1 | bench_validity_mcp.py | 5,500 | 50,352,437 | 100.0% (pre-indexed) |
| bitburner | 1/1 | bench_validity.py | 65,024 | 1,504,232 | 95.7% |
| bitburner | 1/1 | bench_validity_mcp.py | 205 | 1,504,232 | 100.0% |
| librechat | 1/1 | bench_validity.py | 65,024 | 6,316,980 | 99.0% |
| librechat | 1/1 | bench_validity_mcp.py | 1,560 | 6,316,980 | 100.0% |
| elixir | 1/1 | bench_validity.py | 4,096 | 3,060,510 | 99.9% |
| elixir | 1/1 | bench_validity_mcp.py | 6,911 | 3,060,510 | 99.8% |
| otp | 1/1 | bench_validity.py | 102 | 46,463,905 | 100.0% |
| otp | 1/1 | bench_validity_mcp.py | 202 | 46,463,905 | 100.0% |
| go | 1/1 | bench_validity.py | 307 | 36,501,836 | 100.0% |
| go | 1/1 | bench_validity_mcp.py | 19,587 | 36,501,836 | 99.9% |
| kotlin | 1/1 | bench_validity.py | 64,204 | 13,984,544 | 99.5% |
| kotlin | 1/1 | bench_validity_mcp.py | 8,810 | 13,984,544 | 99.9% |
| swift | 1/1 | bench_validity.py | 64,409 | 38,017,250 | 99.8% |
| swift | 1/1 | bench_validity_mcp.py | 5,793 | 38,017,250 | 100.0% |
| rails | 1/1 | bench_validity.py | 64,819 | 5,445,557 | 98.8% |
| rails | 1/1 | bench_validity_mcp.py | 6,601 | 5,445,557 | 99.9% |
| framework | 1/1 | bench_validity.py | 65,024 | 4,218,620 | 98.5% |
| framework | 1/1 | bench_validity_mcp.py | 5,583 | 4,218,620 | 99.9% |
| kong | 1/1 | bench_validity.py | 53,145 | 3,440,558 | 98.5% |
| kong | 1/1 | bench_validity_mcp.py | 97 | 3,440,558 | 100.0% |
| spring-boot | 1/1 | bench_validity.py | 65,024 | 487,802 | 86.7% |
| spring-boot | 1/1 | bench_validity_mcp.py | 448 | 487,802 | 99.9% |
| vue | 1/1 | bench_validity.py | 1,433 | 549,971 | 99.7% |
| vue | 1/1 | bench_validity_mcp.py | 5,738 | 549,971 | 99.0% |

**RESULT: ALL TASKS PASS (15 repos × 2 surfaces).**

- **projectm** (~5,800 files, ~1.1M lines, C++): ~100% token savings; 2K-token map covers `PCM::AddToBuffer`, `Loudness`, `CurrentRelative`, `AverageRelative`.
- **vaultwarden** (~200 Rust files): ~96–99.8% token savings; 33K-token map covers `generate_invite`, `delete_user`, `admin_page`, `hash_password`, `verify_password_hash`, `routes`, `catchers`.
- **linux** (Linux kernel, ~50M tokens full): With `--pre-index pick_next_task` the map narrows to `kernel/sched/` and ships in **~1.1s** (no full-tree walk), covering `pick_next_task`, `schedule`, `update_curr` at 99.9% savings. Use a *specific* probe symbol.
- **bitburner** (TypeScript): 95.7% savings CLI (65K-token map); `loadAliases`/`addAlias` found in both surfaces.
- **librechat** (TypeScript monorepo, `packages/`): needs 65K-token map to surface `getTenantId`/`configCapability` under whole monorepo; still 99.0% savings.
- **elixir** (`lib/iex`): 99.9% savings; `IEx`, `configure`, `configuration` present in both surfaces.
- **otp** (`lib/compiler`): 100% savings at ~102 (CLI) / 202 (MCP) map tokens.
- **go** (`src/cmp`): 100% savings; `Less`/`Compare`/`Or` present in both surfaces.
- **kotlin** (`core`): 99.5% savings CLI (64K-token map); `Variance`/`TypeSystemCommonBackendContext` present in both surfaces. `computeExpandedTypeForInlineClass` excluded (kotlin-grammar blind spot).
- **swift** (`lib`): 99.8% savings CLI (64K-token map).
- **rails** (`activerecord/lib`): 98.8% savings CLI (65K-token map).
- **framework** (`src`): 98.5% savings CLI (65K-token map).
- **kong** (`kong`): 98.5% savings CLI (53K-token map).
- **spring-boot** (build-plugin): 86.7% savings CLI (65K-token map).
- **vue** (`src/v3/reactivity`): 99.7% savings CLI (1.4K-token map).

**Note on the linux slot:** `--pre-index pick_next_task` (CLI) and `pre_index="pick_next_task"` (MCP) narrow the 66k-file kernel to `kernel/sched/*` (~6 files). Without scoping, MCP detect walks all 66k files and is cold-cache-flaky. With scoping: deterministic — verified 3x consecutive PASS.

**MCP token shape differs from CLI:** `bench_validity_mcp.py` exercises `tricorder_detect` (per-file definition records), not a serialized map — MCP "tokens" scale with result count per identifier. projectm MCP tokens are smaller than CLI map (1358 vs 2048); vaultwarden's grow to ~2695. Savings measured against same full-repo estimate in both suites.

**MCP `tricorder_detect` supports `pre_index`** (mirrors CLI `--pre-index`) — linux MCP slot uses `pre_index="pick_next_task"` to narrow to `kernel/sched/*`; runtime dropped from ~168s to ~64s, no longer cold-cache-flaky.

## Running Tests (Agent Instructions)

To run the unit and regression test suite locally:

```bash
# 1. Navigate to the tricorder repo root
cd D:/Projects/tricorder

# 2. Run targeted test suites (CLI, MCP, utilities, regression phase 1)
python -m pytest tests/test_cli_autodiscovery.py tests/test_mcp.py tests/test_utils.py tests/test_regression_phase1.py -v

# 3. Run the full test suite
python -m pytest tests/ -v
```

*Note: Tests insert `.` into `sys.path`, so pytest must be executed from the repository root.*

---

### Reproduce

- **Repos:** projectm (C++), vaultwarden (Rust), Linux kernel, bitburner (`bitburner-src`, TS), LibreChat (`LibreChat`, TS), elixir (`lib/iex`), otp (`lib/compiler`), go (`src/cmp`), kotlin (`core`), swift (`lib`), rails (`activerecord/lib`), framework (`src`), kong (`kong`), spring-boot (build-plugin), vue (`src/v3/reactivity`). projectm at `D:\Projects\projectm`; rest under `D:\Projects\Tricorder-Testing-Repos/<folder>`. bitburner folder is `bitburner-src`.

```bash
# from tricorder repo root, in its venv
python bench/bench_validity.py               # CLI surface (all 15 repos)
python bench/bench_validity_mcp.py           # MCP surface
python bench/bench_validity.py linux         # linux fast-path only
python bench/bench_validity.py bitburner     # single repo by name
python bench/bench_validity.py --root /path/to/your/repos  # custom checkouts
```

Note: `rg` must be on `PATH` for `--pre-index` fast path (linux slot). Task definitions live in `bench/bench_validity*.py`. No CI bench machinery — run locally; numbers reproducible on same public repos.

## Security Model

Tricorder treats **repository content as untrusted input**. A malicious repo can contain prompt-injection attempts, path-traversal filenames, or resource-exhaustion structures.

| Control | Ticket | Behavior |
|---------|--------|----------|
| Trust metadata | TC-005 | Every MCP response stamped `source: scanned_repository`, `trust: untrusted_repository_content`. |
| Content boundary | TC-001 | Raw map wrapped in `BEGIN/END UNTRUSTED REPOSITORY CONTEXT` markers. |
| Path containment | TC-006 | `chat_files` / `detail` file params rejected if they resolve outside `project_root`. |
| `max_files` clamp | TC-007 | MCP `max_files` clamped to 10,000 server-side; discovery early-stops at 20,000. |
| Output containment | TC-008 | `output_file`/`--output` writes contained: server output goes to `get_cache_root()/.tricorder/output/<basename>` (honors `TRICORDER_CACHE_HOME`); `--output` is the sole sanctioned user-chosen path. **All in-process writes route through `utils.safe_write()`, which raises `ValueError` on any target escaping the cache root** — the never-write-to-scanned-repo invariant is enforced structurally, not per-call. |
| Resource envelope | TC-002 | Global budget: max 20k files, 500 MB, depth 25, 300s, 1 MB/file. Limits → partial result + `scan_warning`. Tunable via `TRICORDER_MAX_*` env vars. |
| Cache isolation | TC-003 | Tags cache lives outside the repo (see Caching). |
| Parser timeout | TC-004 | Each tree-sitter parse: 5s hard timeout (`TRICORDER_PARSER_TIMEOUT_S`); hang skipped, not stalled. |
| Dependency pinning | TC-009 | `requirements.txt` fully pinned; `scripts/depscan.py` emits pinned inventory + `pip-audit`. |
| Parser fuzzing | TC-010 | `tests/security/` holds adversarial fixtures (deeply nested, huge line, malformed, unicode, broken, giant string) asserting no crash/hang. |

**Environment overrides (all optional):**

```
TRICORDER_MAX_SCAN_FILES=20000
TRICORDER_MAX_TOTAL_BYTES=524288000
TRICORDER_MAX_SCAN_DEPTH=25
TRICORDER_MAX_SCAN_TIME_S=300
TRICORDER_MAX_SOURCE_FILE_SIZE=1048576
TRICORDER_PARSER_TIMEOUT_S=5
TRICORDER_CACHE_HOME=<tricorder workspace>/.tricorder   # default; controls cache + output root
```

## Supported Languages

**Signature extraction + return types (11 grammars):** Python, JavaScript, TypeScript, C, C++, Java, Go, Rust, Swift, C#, Ruby. Enforced by `tests/test_language_matrix.py` (`test_claimed_languages_extract_defined_signature`).

**Wider parse support (28 total via two query packs):**

- `tree-sitter-language-pack` (29): arduino, c, chatito, commonlisp, cpp, csharp, d, dart, elisp, elixir, elm, gleam, go, hcl, java, javascript, lua, ocaml, ocaml_interface, pony, properties, python, r, racket, ruby, rust, solidity, swift, udev
- `tree-sitter-languages` (22, adds): kotlin, php, ql, scala, typescript (plus re-confirms c, cpp, elixir, elm, go, hcl, java, javascript, ocaml, ruby, rust)

Union = 28 distinct languages. Canonical list in `utils.py` `EXTENSIONS`. `.h` files mapped to `cpp` (cpp grammar is strict superset of C).

**Language registry (ctags_probe.py):** Single source of truth mapping ctags names, tree-sitter keys, extensions, and SCM query files for 24 languages. Shared by ctags pre-index probe and tree-sitter extraction — adding a new language (e.g. Zig) is one registry entry.

**tricorder_detect search modes:** `search_mode` parameter — `"exact"` (whole word), `"substring"` (contains, default), `"regex"` (Python regex). Case-insensitive for exact/substring. Fixes noisy results (e.g. searching "map" no longer returns "mapping"/"bitmap"/"remap").

## Caching

- Cache location: `<tricorder workspace>/.tricorder/cache/<sha1(repo_path|version|config)>/` — **outside the repository** (TC-003). A repo never controls cache state.
- Default cache root is the tricorder workspace `.tricorder` dir (always writable); override with `TRICORDER_CACHE_HOME`.
- Server map output also lands under the cache root (`<cache root>/output`), so it is contained by the same `safe_write()` guard.
- `--output` is the only write that may target a user-chosen path outside the cache root; it still fails gracefully (honest error + stdout fallback) if the path is unwritable.
- `--signature-only` prints 16-char content signature for debugging.

## Lineage & Attribution

1. **Gen 1 — Aider `RepoMap`** (Paul Gauthier): tree-sitter + PageRank.
2. **Gen 2 — RepoMapper** (Paul Davis / pdavis68): standalone CLI + MCP server. Upstream: https://github.com/pdavis68/RepoMapper
3. **Gen 3 — tricorder**: our fork — 8 bug fixes, 123 tests, 10-language signature extraction, cross-file call graph, ctags/rg pre-index probe, Windows compatibility, full rebrand.

Lineage intentionally kept visible. MIT Licensed.

## License

MIT. Based on the RepoMap design from the Aider project; lineage documented above.