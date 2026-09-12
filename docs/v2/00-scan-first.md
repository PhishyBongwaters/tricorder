# Scan first — the mandatory prereq

Every tricorder workflow starts with a populated DB. Nothing else works
without it: turn-0 injection reads the DB, MCP tools attach it, retrieval
flags query it. An unmapped repo only gets the cheap probe digest.

## The three commands

```bash
# 1. Canonical DB (idempotent, prints path, exits)
python tricorder.py --init --root /path/to/repo
# -> /path/to/repo/.tricorder/db/repo.db

# 2. Fill it (serial rising-cap loop; see chunking below)
python chunk_resume.py /path/to/repo
# [chunk 1] cap=5000 scanned=5000/69567 ... exit=0
# ...
# DONE: 69567/69567 files mapped -> .../repo.db

# 3. Fresh session with the repo as root from here on
```

`--init` creates `<root>/.tricorder/db/<name>.db`, applies schema
(`database.py` `_DDL`) and size-based journal mode, and exits. Re-running
is safe; only `--init --wipe` deletes. `--wipe` without `--init` is a
hard error (exit 2).

## Chunking (large repos)

`chunk_resume.py <repo> [--start-cap 5000] [--step 5000] [--timeout 3600]
[--db-path PATH]` shells `tricorder.py --db-path <db> --full --output
<db>.map --max-files <cap> --quiet` with a rising cap and reads
`COUNT(*) FROM file_state` plus tag/ref totals after each chunk.

- `DONE` when scanned == discovered files. Exit 0.
- `STALL` (exit 1) after 2 consecutive chunks with zero growth.
- 50-iteration ceiling; re-run with bigger `--step` past it.
- Serial, one run at a time. Concurrent runs contend on sqlite.
- `--max-files` is a PREFIX cap: a fixed-cap rerun re-hits mapped files
  and adds zero. Coverage grows only when the cap exceeds mapped count.
- `--db-path` resumes a custom DB; default is the `--init` canonical path.

## Verify coverage yourself

```sql
SELECT COUNT(*) FROM file_state;              -- scanned files
SELECT COUNT(DISTINCT rel_file) FROM tags;    -- files with symbols
SELECT COUNT(*) FROM tags; SELECT COUNT(*) FROM refs;
SELECT COUNT(*) FROM meta;                    -- must be exactly 1
```

`file_state` (not tags) is the coverage measure: tagless files
(`x = 1`) scan fine but own zero tag rows. `meta` holding more than one
row means stacked scans — `reset()` failed to run; wipe and rescan.

## Gotchas

- Never open a possibly-absent DB with `sqlite3.connect` in tooling: it
  creates a 0-byte file, masking real absence. Check existence first.
- Killing a scan: kill the actual `tricorder.py` python PID, not the
  terminal wrapper — children survive wrapper kills.
- `pre_scan.py` is the batch corpus builder (testing-repos + `--extra`),
  not the daily path. Its `--db-dir/--repos-dir/--tricorder` flags
  override the defaults; `--dry-run` lists without scanning.
