# User Guide

Everything you need to install, run, and get value out of tricorder —
whether you're a human at a terminal or an agent via MCP.

- [Installation](#installation)
- [Your first scan](#your-first-scan)
- [The escalation ladder](#the-escalation-ladder)
- [Working with large repositories](#working-with-large-repositories)
- [MCP server setup](#mcp-server-setup)
- [Lifecycle plugins (Hermes / DSH)](#lifecycle-plugins)
- [Caching: how it works](#caching-how-it-works)
- [Configuration reference](#configuration-reference)
- [Troubleshooting](#troubleshooting)
- [FAQ](#faq)

## Installation

**Requirements:** Python 3.11+. `rg` (ripgrep) on `PATH` is recommended for
the pre-index fast path — without it, `ctags` (Universal Ctags) is used as a
fallback probe when available.

```bash
git clone https://github.com/PhishyBongwaters/tricorder
cd tricorder

# Windows
python -m venv .venv
.venv\Scripts\activate
pip install -e .

# Linux / macOS
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

This provides two commands: `tricorder` (CLI) and `tricorder-mcp` (MCP server).
Verify with:

```bash
tricorder --help | head -5
tricorder /path/to/a/small/repo --map-tokens 1024
```

**Dependencies** are pinned in `requirements.txt` (tiktoken, networkx,
tree-sitter + language packs, diskcache, fastmcp, pygments, grep-ast).
Run `pip install -r requirements.txt` instead of `-e .` if you only want the
libraries without the installed scripts.

## Your first scan

```bash
tricorder /path/to/repo
```

You'll get a ranked map of definitions, highest-PageRank first, fitted to
8192 tokens. Try these next:

```bash
tricorder /path/to/repo --map-tokens 2048     # smaller budget
tricorder /path/to/repo --tier 1              # definitions + 3 lines context
tricorder /path/to/repo --mermaid --top 10    # dependency flowchart
tricorder /path/to/repo --top 20 --format json # top 20 tags as JSON
```

**Targeting a subsystem** beats scanning everything:

```bash
tricorder /path/to/repo/src/auth --map-tokens 2048
tricorder /path/to/repo --chat-files src/auth/login.py --other-files src/auth/
```

`--chat-files` (what you're editing) outranks `--mentioned-files`
(what you named) outranks `--other-files` (background context).

**Finding one symbol** — don't scan at all:

```bash
# via MCP: tricorder_detect with query="authenticate"
# via CLI: narrow first, then read the map
tricorder /path/to/repo/src --map-tokens 1024 | grep -i authenticate
```

## The escalation ladder

Each rung costs more tokens than the last. Stop at the first one that
answers your question:

| Rung | Tool / flag | Cost | Answers |
|---|---|---|---|
| 1. Map | `tricorder_scan` / `tricorder .` | ~14 tokens/tag | "Where is the auth code?" |
| 2. Detect | `tricorder_detect` | ~1–2 tokens/tag | "Where is `authenticate` defined?" |
| 3. Symbols | `tricorder_symbols` | structured | "List all classes in `db/`" |
| 4. Detail | `tricorder_detail` | ~50–400 tokens typical (≤2048 default budget) | "What does it do? Who calls it?" |
| 5. Tier-1 scan | `--tier 1` | ~350 tokens/tag | "Show me this subsystem's shape" |
| 6. Full file | read the source | full cost | Last resort |

**Detect search modes:** `tricorder_detect` takes `search_mode` —
`"exact"` (whole word), `"substring"` (contains, default), `"regex"`.
Searching `"map"` in substring mode matches `"mapping"` and `"bitmap"` —
switch to `"exact"` when that's noise.

**Graph queries** collapse multi-hop questions into one call:

```
callers('authenticate') depth=2
callees('main') depth=1 exclude=tests/**
refs('Config') type=class limit=50
```

## Working with large repositories

**Pre-index probe.** For a known symbol in a giant tree, never do a full
scan first:

```bash
tricorder /path/to/linux --pre-index "pick_next_task" \
    --pre-index-max-files 20 --map-tokens 2048
```

How it works: `rg -l -w SYMBOL` with multi-language globs narrows the file
set *before* any tree walk (the Linux kernel narrows to ~6 files in
`kernel/sched/` in ~1.1s). Ctags is only a fallback if rg finds nothing;
ctags index builds are refused past 20,000 source files.

Rules of thumb:
- Pick a **specific** symbol. `pick_next_task` works; `schedule` (thousands of hits) caps out and misses.
- `--pre-index-max-files` (default 100) caps probe results; `--pre-index-include-parents N` pulls in N parent dirs for context.
- Same params exist on MCP `tricorder_scan` / `tricorder_detect`.

**Excluding vendored code:**

```bash
tricorder . --exclude-globs 'vendor/**' 'third_party/**' 'node_modules/**'
```

Globs are POSIX, relative to `--root`, and applied *before* ranking so
first-party code dominates the map.

**Resource envelope.** Every scan is bounded by depth 25 and 1MB per file;
file count, total bytes, and scan time are unlimited by default so full-repo
maps (including `--full`) are never silently truncated. Set
`TRICORDER_MAX_SCAN_FILES`, `TRICORDER_MAX_TOTAL_BYTES`, or
`TRICORDER_MAX_SCAN_TIME_S` to impose caps; hitting a cap yields a partial map
plus a warning — on MCP responses a `scan_warning` field, on the CLI via
stderr — never a silent truncation. Tune via `TRICORDER_MAX_*` env vars
(see [Configuration](#configuration-reference)).

**Huge single scan to disk:**

```bash
tricorder /path/to/repo --full --output /tmp/full-map.txt
```

## MCP server setup

```bash
tricorder-mcp     # STDIO; keep it running or let your client spawn it
```

**Claude Code / Cline** (`cline_mcp_settings.json`):

```json
{ "mcpServers": { "tricorder": {
    "command": "/absolute/path/to/.venv/Scripts/tricorder-mcp.exe",
    "type": "stdio", "disabled": false, "timeout": 60, "args": []
} } }
```

**Hermes** (`~/.hermes/config.yaml`):

```yaml
mcp_servers:
  tricorder:
    command: "C:/absolute/path/to/tricorder/.venv/Scripts/tricorder-mcp.exe"
    args: []
```

Then restart Hermes. Requires the `mcp` Python package.

**Agent skill.** `skills/tricorder/SKILL.md` teaches the escalation ladder.
Copy it where your agent reads skills from. For DSH, use
`skills/tricorder-dsh/SKILL.md`.

Full tool reference: [MCP Reference](mcp-reference.md).

## Lifecycle plugins

The plugins inject a **turn-0 steering line** at session start — never a full map.
If a pre-scan DB covers the project, it reports coverage plus tool steering
from sqlite (no filesystem walk); otherwise it falls back to a cheap probe
digest (language tally, file count, line estimate, MCP pointer) marked
"(not pre-mapped; probe only)".

**Hermes** (`plugins/tricorder/`):

```bash
hermes plugins install "http://127.0.0.1:3001/projects/tricorder.git#plugins/tricorder" --force --enable
hermes config set plugins.entries.tricorder.active_project D:/Projects/<repo>
```

Slash commands: `/tricorder root <path>`, `/tricorder scan [path]`,
`/tricorder status`. Config keys: `active_project` (required),
`exclude_globs` (list).

**DSH** — two pieces: the turn-0 injector (`plugins/dsh-tricorder-inject/`,
vendored Cordis plugin → `node_modules/@deepseek-ai/dsh-tricorder-inject`,
enabled in `cordis.patch.yml`) and the MCP tools + skill
(`skills/tricorder-dsh/SKILL.md`, server registered as `tricorder` via
`dsh-mcp-client`).

**Cache validity** is stat-based, not TTL: the CLI's `--signature-only`
computes sha256 over `{path}:{size}:{mtime}` per file; the plugin compares
against the stored signature and rebuilds on mismatch.

## Caching: how it works

All caches live **outside the scanned repo** (default
`<tricorder workspace>/.tricorder/`; override with `TRICORDER_CACHE_HOME`).
A repo can never control cache state.

| Layer | What | Invalidation |
|---|---|---|
| Tags diskcache | Per-file tag bundles | Content signature (`{path}:{size}:{mtime}` sha256) |
| Cross-ref index | Import-resolved call graph, `__cross_ref_index_v1__` | Fingerprint over sorted `(rel path, mtime)`; any add/edit/delete rebuilds |
| Tag DB | sqlite (`:memory:`, `--db-path`, or `--init`) | `EXTRACTOR_VERSION` stamp — extractor changes force full rescan |

Useful commands:

```bash
tricorder /path/to/repo --signature-only   # 16-char content signature
tricorder /path/to/repo --force-refresh    # bust all caches, rescan
tricorder /path/to/repo --db-coverage      # mapped-DB coverage line
tricorder /path/to/repo --init             # canonical DB at <root>/.tricorder/db/
```

## Configuration reference

All optional env vars:

| Var | Default | Purpose |
|---|---|---|
| `TRICORDER_CACHE_HOME` | `<workspace>/.tricorder` | Cache + output root |
| `TRICORDER_MAX_SCAN_FILES` | `0` (unlimited) | Max files per scan; set to cap |
| `TRICORDER_MAX_TOTAL_BYTES` | `0` (unlimited) | Max total bytes; set to cap (e.g. `524288000` for 500MB) |
| `TRICORDER_MAX_SCAN_DEPTH` | `25` | Max walk depth |
| `TRICORDER_MAX_SCAN_TIME_S` | `0` (unlimited) | Max scan seconds; set to cap |
| `TRICORDER_MAX_SOURCE_FILE_SIZE` | `1048576` | Max bytes per file (1MB) |
| `TRICORDER_MAX_ALLOWED_FILES` | `10000` | MCP `max_files` clamp |
| `TRICORDER_PARSER_TIMEOUT_S` | `5` | Per-file tree-sitter timeout |
| `TRICORDER_WALK_WORKERS` | auto | Directory-walk parallelism |

## Troubleshooting

**"No symbols found" / empty map.** Check the language is supported
(`utils.CODE_EXTENSIONS`, 34 languages with tree-sitter queries) and the files aren't excluded by
`--exclude-globs`. Umbrella headers with no symbols correctly yield zero tags.

**Scan is slow on a huge repo.** Use `--pre-index SYMBOL` to narrow first;
raise `--max-files` only if you mean it; check `--stats-only` for the
token math before committing to a full map.

**Stale results after editing.** The stat signature should invalidate
automatically; if not, `--force-refresh`. Note mtime is second-resolution —
a sub-second edit preserving file size won't invalidate (documented
trade-off; content hashing is the escape hatch).

**MCP `max_files` ignored.** It's clamped to 10,000 server-side (TC-007).

**`--wipe` errors.** It requires `--init`: `tricorder . --init --wipe`.

**Windows paths.** Use absolute paths everywhere; the MCP server rejects
relative `project_root`. The test/bench harnesses accept `TRICORDER_TESTBED`
etc. to override machine-specific paths.

## FAQ

**Does it call any model or network?** No. Tree-sitter, sqlite, and
arithmetic, on the local machine.

**Where does my data go?** Nowhere. Maps render to stdout (or `--output`);
caches stay under `TRICORDER_CACHE_HOME`. Scanned repos are never written to
— enforced structurally by `utils.safe_write()`.

**Which languages get signatures?** Python, JavaScript, TypeScript, C, C++,
Java, Go, Rust, Swift, C#, Ruby — enforced by
`tests/test_language_matrix.py`. 34 languages parse overall.

**Why do Python methods show as `Renderer::render` in the map but `render`
in `tricorder_symbols`?** Deliberate: tags qualify every language with
`::`; symbol records keep Python bare. All lookups normalize, so both
resolve to the same symbol. Details in
[class-context-qualification](class-context-qualification.md).

**Can I use it without the MCP server?** Yes — the CLI is fully
self-sufficient. The MCP server is a thin wrapper over the same engine.
