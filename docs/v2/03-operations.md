# Operations — invariants, ceilings, gotchas

## DB invariants (guarded by `tests/test_db_invariants.py`)

- `SELECT COUNT(*) FROM meta` == 1. More rows = stacked scans.
- `reset()` clears all six tables together. Partial
  clears are a corruption vector — never add one.
- `file_state` keys ⊇ walked files and == `mapped_rels()` (the resume
  set). `COUNT(*) FROM file_state` is coverage; tags-distinct is not
  (tagless files).
- `populate_refs()` output is stable across reruns (DELETE + INSERT,
  no accumulation); `stop_names` persists the skipped set with it.
- `sync_file_flags`: tagless files carry a reason, tagged files carry
  none (tagged wins on conflict).

## Hard ceilings (ponytail markers in code)

- Stop-names: def in >50 files gets no ref edges. Fixed 50; raise it
  only with a measured false-negative case.
- Chunk loop: 50 iterations max, default step 5000 (≈250k files).
- Parser: `TRICORDER_PARSER_TIMEOUT_S=5` per file.
- Journals: DELETE >500MB existing DB, WAL below, MEMORY for `--no-db`.
- `--max-files 0` = uncapped. Only for small repos or the final chunk.

## Failure signatures

- `STALL` in chunk loop with scanned < discovered → usually tagless
  files miscounted (fixed: measure file_state) or a genuinely stuck
  parse; check stderr tail printed with the STALL line.
- Runaway `refs` growth → a stop-name escaped the guard. Check
  `SELECT name, COUNT(*) FROM refs GROUP BY name ORDER BY 2 DESC`.
- `meta` root mismatch → DB belongs to another checkout. `--init
  --wipe` and rescan; never hand-edit.
- Empty map, files present → tree-sitter lacks the grammar. Install
  the language pack; the warning names it.

## Layout

- `<repo>/.tricorder/db/<repo>.db` — per-repo sqlite (canonical).
- `<repo>.map` beside it — rendered output. Both gitignored
  (`.tricorder/`).
- `.tricorder.tags.cache.v1/` — per-file parse cache.
- `TRICORDER_CACHE_HOME` relocates the shared cache root.
- Full suite: `pytest tests/` from repo root (repo `.venv`).
