# Tricorder — DB-backed repo mapper

Maps a repository (files → symbols → ranked map) without holding the
whole tree in RAM. Parse results go straight into sqlite; ranking reads
back out of it.

## Install

```bash
python -m venv .venv && .venv/Scripts/pip install -e .   # Windows
# provides: tricorder, tricorder-mcp
```

Requires Python ≥3.11 and `rg` (ripgrep) on PATH. Full fresh-system guide:
`05-setup.md`.

## Test

```bash
.venv/Scripts/python.exe -m pytest tests/ -q -p no:cacheprovider
```

## Docs

`00-scan-first.md` · `01-pipeline.md` · `02-tiering-and-retrieval.md` ·
`03-operations.md` · `04-internals.md` · `05-setup.md`

## Use

```bash
tricorder --init --root /path/to/repo
python chunk_resume.py /path/to/repo     # to DONE
tricorder <path> --db-path <db> --tier 0 # orient, defs only
```

Scan first — everything else reads the DB. Session recipe, tiering,
and MCP/CLI split: `00-scan-first.md`, `02-tiering-and-retrieval.md`.

## How it works

Tree-sitter parse per file → tags into sqlite → name-resolved ref
edges → SQL PageRank → token-budgeted map. Incremental via per-file
size+mtime; resume is just re-running. Full pipeline:
`01-pipeline.md`, machinery: `04-internals.md`, operations:
`03-operations.md`.

## Status

`dev/db-map` branch. CLI is the stable surface; MCP server and both
turn-0 plugins (Hermes, DSH) are ported to the DB but live-session
verification is pending. No benchmark numbers are claimed on this
branch until re-measured.

## License

MIT (see LICENSE). Fork of RepoMapper (RepoMap design from Aider).
