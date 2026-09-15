# Tricorder — repository maps that fit in context

Tricorder scans a codebase and returns the parts that matter: every
definition and reference, ranked so the significant code fits inside
a fixed token budget. No model calls, no network access. Tree-sitter,
sqlite, and arithmetic, on the local machine.

```bash
git clone https://github.com/PhishyBongwaters/tricorder
cd tricorder
pip install -e .
python tricorder.py --root /path/to/repo --tier 0
```

Point it at a directory. It walks the tree, parses each source file,
and prints the highest-ranked symbols first — prototypes, signatures,
and cross-file references — stopping when the budget runs out.

## Purpose

Language models working in large repositories exhaust their context
before reasoning begins if the whole tree is loaded. Tricorder takes
the opposite approach: retrieve, do not dump. An agent locates one
symbol, reads its shape, pulls its body and callers, and opens the
source file. Each step spends tokens deliberately, in ascending order
of response cost.

## Installation

Requires Python 3.11 or later (see `pyproject.toml`). The procedure
is the clone and install shown above; `.[dev]` in place of `.`
adds the test dependencies.

Parsing depends on `grep-ast` and tree-sitter grammars (installed as
package dependencies). Symbol pre-indexing uses `ripgrep` and
`ctags` from `PATH` where available; both are optional, with
`ripgrep` substring search as the fallback path.

## Interfaces

**Command line.** Map a repository, price a map before building it,
scan in capped runs, audit coverage afterwards. Task-organized
reference: [`04-cli-reference.md`](04-cli-reference.md).

```bash
tricorder.py . --map-tokens 2048          # map this repo, tight budget
tricorder.py --dry-run .                  # price it first
tricorder.py --db-path ./db/repo.db --max-files 5000 .
python bench/coverage_audit.py            # check the scan finished
```

**Model Context Protocol server.** Five tools in ascending response
cost: locate the name, read its shape, pull body plus callers,
traverse the call graph, map as a last resort. A turn-0 injection
orients a fresh session before it asks anything. Agent-oriented
detail: [`03-agent-retrieval.md`](03-agent-retrieval.md).

```
tricorder_detect   → identifier locations
tricorder_symbols  → symbol shape
tricorder_detail   → body, callers, callees
tricorder_query    → callers('x') depth=2 | callees('y')
tricorder_scan     → the budgeted map, inline or to disk
```

## Architecture

1. **Discover** — one shared file walk (gitignore-aware; dotfiles
   and build directories skipped). Every surface uses it.
2. **Parse** — tree-sitter per file: definitions and references
   become flat `(file, line, name, kind)` tags, with a per-file
   parse timeout. Failures skip with a warning.
3. **Persist** — tags land in sqlite behind a per-file dirty bit,
   so rescans re-parse only changed files and capped runs resume
   where they stopped.
4. **Rank** — PageRank over the reference graph, computed in SQL,
   so significant files surface first inside any token budget.
5. **Render** — definitions only (cheapest), or definitions plus
   source context, as text, JSON, or Mermaid.

Technical documents, each derived from the code:

- [`01-scan-pipeline.md`](01-scan-pipeline.md) — the five stages,
  file by file, including capped runs on large trees.
- [`02-db-and-state.md`](02-db-and-state.md) — tables, freshness
  layers, version stamps, caches, database locations.
- [`03-agent-retrieval.md`](03-agent-retrieval.md) — the five MCP
  tools, escalation signals, turn-0 injection.
- [`04-cli-reference.md`](04-cli-reference.md) — flags by task,
  companion scripts, environment knobs.
- [`05-plugins-and-skills.md`](05-plugins-and-skills.md) — Hermes
  and DSH plugins (turn-0 injection, slash commands) and skills
  (agent guidance).

## Lineage

1. **Aider `RepoMap`** — tree-sitter plus PageRank for context
   compression.
2. **RepoMapper** — standalone CLI plus MCP server.
   Upstream: https://github.com/pdavis68/RepoMapper
3. **Tricorder** — this fork: sqlite-backed flat-memory scanning,
   cross-file call graph, pre-index probing, extractor versioning,
   Windows support.

## Guarantees

- Deterministic: the same repository and the same code produce the
  same map. Approximate matches are flagged `fuzzy`, never passed
  off as exact.
- Local: identifiers never leave the machine. No accounts, no keys.
- Explicit about gaps: untagged files carry a recorded reason,
  truncated maps report it (`tier_hint`), and scans whose
  extractor moved on are flagged, not served silently.

## License

See LICENSE in the repository root.
