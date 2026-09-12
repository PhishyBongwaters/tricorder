# AGENTS.md — tricorder (dev/db-map)

DB-backed repo mapper: source → tree-sitter tags → sqlite → PageRank →
ranked map. Flat-memory walk; the DB is the memory.

## First: scan before anything

```bash
.venv/Scripts/python.exe tricorder.py --init --root <repo>   # canonical DB, prints path
.venv/Scripts/python.exe chunk_resume.py <repo>              # serial rising-cap loop to DONE
.venv/Scripts/python.exe -m pytest tests/ -q -p no:cacheprovider   # 206 passed
```

Use the repo `.venv` (pytest + grammars). No DB = no map, no tools.

## Rules

- One run at a time. Concurrent scans contend on sqlite. No background
  loops; the user kills them.
- Coverage = `COUNT(*) FROM file_state`, never tags-distinct (tagless
  files own zero tag rows). `meta` must hold exactly 1 row.
- `--max-files` is a PREFIX cap: fixed-cap reruns add zero. Rising caps
  only (`chunk_resume.py` enforces this).
- Navigate with detect → symbols → detail; open exact file lines before
  asserting or editing anything the map found.
- Never hardcode repo names/paths in app code — argv, CLI flags, size
  rules. Never `sqlite3.connect` a possibly-absent DB (creates a
  0-byte stub); check existence first.
- No destructive commands (rm, wipes) without explicit approval.
- Depth: `docs/v2/` (00 scan-first, 01 pipeline, 02 tiering+retrieval,
  03 operations). MCP server + turn-0 plugins are unported — document
  as TBD, no usage claims.
