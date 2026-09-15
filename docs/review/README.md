# Tricorder — a repo map that fits in context

Tricorder scans a codebase and hands you (or your agent) the parts that
matter: every definition, every reference, ranked so the important
code lands inside a fixed token budget. No model calls, no network, no
VRAM — tree-sitter, sqlite, and arithmetic, on your own machine.

```bash
git clone https://github.com/PhishyBongwaters/tricorder
cd tricorder
pip install -e .
python tricorder.py --root D:/Projects/projectm --tier 0
```

Point it at any directory. It walks the tree, parses every source file,
and prints the highest-ranked symbols first — prototypes, signatures,
and cross-file references — stopping when the budget runs out (verified:
83,000 files scanned to sqlite on the linux tree; maps render inside a
fixed token budget, priceable up front with --dry-run).

## Why

Language models drown in large repos: stuff the whole tree in context
and you burn the window (or the GPU) before reasoning starts. Tricorder
is the opposite move — retrieve, don't dump. An agent locates one
symbol, reads its shape, pulls its body and callers, and opens the real
file. Each step costs tokens on purpose, cheapest first, stopping at the
first step that answers.

## Install

Requires Python 3.11+ (from `pyproject.toml`); the quick block at the
top is the whole procedure (use `.[dev]` instead of `.` for pytest).
What it pulls in:

 Parsing needs `grep-ast` + tree-sitter grammars (installed as
 dependencies); symbol search needs `ripgrep` and `ctags` on PATH for
 the fast pre-index path (optional but recommended on huge trees).

## Use it two ways

**Humans — the CLI.** Map a repo, price a map before building it, scan
in capped chunks, audit coverage afterwards. Full task-organized
reference: [`04-cli-reference.md`](04-cli-reference.md).

```bash
tricorder.py . --map-tokens 2048          # map this repo, tight budget
tricorder.py --dry-run .                  # price it first
tricorder.py --db-path ./db/repo.db --max-files 5000 .
python bench/coverage_audit.py            # prove the scan finished
```

**Agents — the MCP server.** Five tools, cheapest first: locate the
name, read its shape, pull body + callers, traverse the call graph, map
as a last resort. Plus turn-0 injection that orients a fresh session
before it asks anything. Agent-oriented detail:
[`03-agent-retrieval.md`](03-agent-retrieval.md).

```
tricorder_detect   → where is this identifier?
tricorder_symbols  → what is its shape?
tricorder_detail   → body + callers + callees
tricorder_query    → callers('x') depth=2 | callees('y')
tricorder_scan     → the budgeted map (or to disk)
```

## How it works (short version)

1. **Discover** — one shared file walk (gitignore-aware, dotfiles and
   build dirs skipped). One implementation, every surface uses it.
2. **Parse** — tree-sitter per file: definitions and references become
   flat `(file, line, name, kind)` tags. 5-second timeout per file;
   failures skip with a warning, never fatal.
3. **Persist** — tags land in sqlite with a per-file dirty bit, so
   rescans re-parse only what changed and chunked scans resume where
   they stopped.
4. **Rank** — PageRank over the reference graph, computed in SQL, so
   the important files surface first inside any token budget.
5. **Render** — definitions-only (cheapest) or definitions plus source
   context, as text, JSON, or Mermaid.

Deep dives, each derived from the code and nothing else:

- [`01-scan-pipeline.md`](01-scan-pipeline.md) — the five stages,
  file by file, including the large-repo chunk protocol.
- [`02-db-and-state.md`](02-db-and-state.md) — tables, freshness
  layers, version stamps, caches, and where DBs live.
- [`03-agent-retrieval.md`](03-agent-retrieval.md) — the five MCP
  tools, the escalation ladder, turn-0 injection.
- [`04-cli-reference.md`](04-cli-reference.md) — every flag, by task,
  plus companion scripts and environment knobs.

## Guarantees

- Deterministic: same repo + same code = same map. Fuzzy matches are
  flagged `fuzzy`, never silently passed as exact.
- Local: identifiers never leave the box. No accounts, no API keys.
- Honest about gaps: untagged files are explained (no grammar, empty,
  parsed-but-symbol-free), truncated maps say so (`tier_hint`),
  stale scans are flagged, not served silently.

## License

See LICENSE in the repo root.
