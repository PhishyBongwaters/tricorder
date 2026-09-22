# Tricorder — Code Intelligence Scanner

[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-463%20passed%2C%204%20skipped-brightgreen.svg)](tests/)

**Turn any codebase into a token-efficient map an LLM agent can actually navigate.**

Tricorder scans a repository with tree-sitter, ranks every symbol by importance (PageRank over the call graph), and emits a compact map — definitions, signatures, and cross-file references — sized to fit your context window. Measured on the current pipeline in scripted retrieval runs (fixed detect/symbols/detail rungs, no live agent): Vaultwarden queries cost 8,987 response-payload tokens vs 26,818 for baseline navigation (−66.5%), and 5 Swift queries cost 7,608 tokens where the baseline needs 38,885 (−80.4%).

```
$ tricorder /path/to/repo --map-tokens 2048

src/database.py (24 lines)

  1: class Database:
  7:     def get_connection(self) -> Connection:
 11:     def execute(self, query: str) -> Result:

src/server.py (18 lines)

  1: class Server:
  5:     def handle_request(self, req: Request) -> Response:
```

Three interfaces, one engine: a **CLI** for humans and scripts, an **MCP server** for any MCP client (Hermes, Cline, Claude Code), and **lifecycle plugins** that inject a navigation digest at session start.

## Why Tricorder

| Without it | With it |
|---|---|
| Read every file (hours) | Intelligent map in seconds |
| Hit-or-miss grep | Precise symbol detection with definitions *and* references |
| Manual dependency tracing | Automatic call graph + PageRank |
| Context window overflow | Token-budgeted output (−55% to −80% per-query payload vs baseline tools, measured) |

**Measured on the current pipeline (response-payload tokens in scripted retrieval runs — fixed detect/symbols/detail rungs, ground-truth citation grading, no live agent):** −70.3% combined across Vaultwarden, Go, and Swift repos — ground truth cited in 12/12 runs on both baseline and branch (Vaultwarden/Go measured 2026-09-21, Swift re-measured 2026-09-22 after the Q4 crowding fix; see [comparison runs](eval/comparison-runs/2026-09-22/README.md)). This is distinct from end-to-end agent eval (`bench/bench_agent_eval.py`, model in the loop) — no agent-eval numbers are quoted here. Older Gen 2 map-vs-blind-repo numbers (86.7–100% across 15 repos) describe a previous pipeline version and are kept for history in [Benchmarks](docs/benchmarks.md).

## Quick Start

```bash
# Requires Python 3.11+ (the --pre-index fast path is ripgrep-first;
# a ctags index is the fallback when rg isn't on PATH)
git clone https://github.com/PhishyBongwaters/tricorder
cd tricorder
python -m venv .venv
.venv/Scripts/pip install -e .        # Windows
# .venv/bin/pip install -e .          # Linux/macOS

tricorder /path/to/your/repo          # Map it
tricorder /path/to/your/repo --mermaid --top 10   # Dependency flowchart
```

That's it. No config files, no model keys, no network calls — everything runs locally.

## Features

- **Tree-sitter parsing, 93 validated languages** — 11 with full signature + return-type extraction (Python, JS/TS, C, C++, Java, Go, Rust, Swift, C#, Ruby)
- **Class-context qualification** — methods scoped as `Class::method` from AST structure, identical across sequential and parallel scans
- **PageRank ranking** — the important code surfaces first, inside your token budget
- **Token-aware output** — binary search fits the map to `--map-tokens`; tiers (T0 definitions → T1 with context) let you stop at the cheapest rung that answers the question
- **Pre-index probe** — `--pre-index SYMBOL` narrows giant trees via ripgrep in ~1s (no full walk)
- **Graph query DSL** — `callers('auth') depth=2 exclude=tests/**` replaces 5+ round-trips; `tests_for('x')` finds covering tests
- **One-call locate** — `tricorder_locate` runs detect → detail in a single round trip with a token budget
- **Delta maps** — `tricorder_diff` / `--diff` (alias `--since`) shows what changed since the last scan (read-only)
- **Budget-aware detail** — `tricorder_detail(max_tokens=…)` trims body → callees → callers, never identity
- **Cross-file call graph** — import-resolved callers/callees, persisted across processes
- **DB-backed scanning** (after `--init`; a fresh repo with no index scans in-memory) — tags stream into sqlite; extractor versioning forces rescan when the parser changes
- **Content-aware caching** — cache lives outside the repo; stat-based signatures invalidate on change
- **Security model** — repo content treated as untrusted input (path containment, output containment, resource envelopes)

## Documentation

| Doc | Contents |
|---|---|
| [User Guide](docs/user-guide.md) | Installation, workflows, tiers, pre-index, caching, troubleshooting, FAQ |
| [How a Scan Works](docs/how-a-scan-works.md) | Plain-language walkthrough of what happens when you scan a repo |
| [CLI Reference](docs/cli-reference.md) | Every flag, with examples |
| [MCP Reference](docs/mcp-reference.md) | All 7 tools, parameters, response shapes |
| [Architecture](docs/architecture.md) | Pipeline, DB design, ranking, graph, caching, security |
| [Class-Context Qualification](docs/class-context-qualification.md) | Deep dive on `Class::method` scoping |
| [Benchmarks](docs/benchmarks.md) | Methodology, full results, reproduce steps |

## MCP Server

```bash
tricorder-mcp          # STDIO server; register in your MCP client
```

```json
// cline_mcp_settings.json
{ "mcpServers": { "tricorder": {
    "command": "/absolute/path/to/.venv/Scripts/tricorder-mcp.exe",
    "type": "stdio", "args": [] } } }
```

Seven tools: `tricorder_scan`, `tricorder_detect`, `tricorder_symbols`, `tricorder_detail`, `tricorder_query`, `tricorder_diff`, `tricorder_locate`. Full reference in [MCP Reference](docs/mcp-reference.md). A bundled skill (`skills/tricorder/SKILL.md`) teaches agents the escalation ladder: map → detect → detail → tier-1 → full file.

## The Escalation Ladder

Spend tokens deliberately, cheapest first (tier costs are rough rules of
thumb, not measurements — measured end-to-end savings are above):

```
1. MAP    (~14 tokens/tag)  → "Database classes in database.py"
2. DETECT (~1-2 tokens/tag) → "Found getConnection() at database.py:42"
3. DETAIL (~50-400 tokens typical, ≤2048 budget)  → Full function + callers
4. T1 SCAN (~350 tokens/tag)→ 3 lines context around each definition
5. FULL FILE (last resort)  → Read the source when necessary
```

## Security

Tricorder treats **repository content as untrusted input**. Every MCP response is stamped `source: scanned_repository` / `trust: untrusted_repository_content`; raw maps are wrapped in `BEGIN/END UNTRUSTED REPOSITORY CONTEXT` markers. Path containment, output containment (`safe_write()` — the never-write-to-scanned-repo invariant is structural), resource envelopes, and parser timeouts are all enforced. Details in [Architecture](docs/architecture.md#security-model).

## Contributing

```bash
.venv/Scripts/python -m pytest tests/ -q -p no:cacheprovider   # full suite
```

463 tests passing, 4 skipped on Windows (all POSIX-only semantics; Linux runs the mirror image with 1 skip on the Windows-only path test), 96 subtests. Platform-specific cases use `skipif` guards or branched fixtures; symlink tests need Windows Developer Mode (or an elevated shell). Bug reports and PRs welcome — please include a failing test where practical. See [AGENTS.md](AGENTS.md) for repo conventions.

## Lineage

1. **Gen 1 — Aider `RepoMap`** (Paul Gauthier): tree-sitter + PageRank.
2. **Gen 2 — RepoMapper** (Paul Davis): standalone CLI + MCP server. Upstream: https://github.com/pdavis68/RepoMapper
3. **Gen 3 — tricorder**: this fork — 463 tests, 93 validated languages, cross-file call graph, ctags/rg pre-index probe, Windows compatibility, DB-backed ranking with extractor versioning.

Lineage intentionally kept visible. MIT Licensed — see [LICENSE](LICENSE).
