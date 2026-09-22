# SPEC — DB-Backed Map (dev/db-map)

**Branch:** `dev/db-map`
**Status:** Working SPEC — living document for the DB-backed map rework.
**Goal:** Eliminate the whole-repo-in-RAM memory blowup on large repos (→ OOM/death
  before `--output` writes) by persisting per-file parse results + the reference
  graph to an on-disk DB, so the tree walk stays fla, PageRank runs against the DB,
  and the map is streamed to output incrementally.
**Constraint:** Nothing merges to `main` until individually validated. No changes to
  `main` are approved.

---

## 1. Problem (measured)

Current pipeline (`core.py`), all in one in-memory pass before anything is written:

1. `discover_src_files` — tree walk → file list
2. `get_ranked_tags` (core.py:1439) — for every file: parse (tree-sitter) → build
   `defines`/`references`/`definitions` name→file dicts → build `nx.MultiDiGraph`
   (node per file, **one edge per cross-file reference**) → **PageRank** → emit
   `ranked_tags` list of `(rank, Tag)` tuples, one per definition.
3. `to_tree`/`render_tree` — assemble the giant output string in memory.
4. `--output` writes **only after** the whole tree is built.

Measured RSS (real pipeline via `scripts/mem_probe.py`):

| Repo | Files | Tags | RSS after walk | Traced peak | Time |
|------|-------|------|----------------|-------------|------|
| vaultwarden | 100 | 219 | 47 MB | 2 MB | 0.1 s |
| go | 2,500 | 56,303 | 187 MB | 157 MB | 7.7 s |
| go | 6,000 | 111,010 | 283 MB | 564 MB | 19 s |
| go@2,500 `--full` | 2,500 | 56,303 | 237 MB (after to_tree) | 157 MB | +8 s |
| kotlin | 57,161 | — | ballooned → killed | — | — |
| kotlin @1,000 | 1,000 | 3,690 | 68 MB | 16 MB | 1.3 s |

Key finding: kotlin at 1,000 files is only 68 MB — the blowup is **pure scale**, not
language. Memory grows roughly linearly with the count of in-memory `(rank, Tag)`
tuples + the `nx` graph over all files/refs, all held until ranking finishes. At
~111 K tags (go@6k) RSS is 283 MB and climbs; at 57 K files the graph + tag dicts
fill the box before `--output` ever runs.

Memory scales super-linearly. A correctly-ordered map cannot be streamed mid-walk
because page rank depends on references from not-yet-parsed files. The "incremental
append during the walk" idea alone cannot work; the DB pivot is the real fix.

## 2. Why a DB

If tags/edges persist incrementally into a DB as each file is parsed (row per
`(file, tag, line, kind)` + edge rows):

- **Flat tree-walk memory** — parse file → insert rows → drop the AST. Per-file parse
  results (currently in `diskcache`) become DB rows, not RAM dicts.
- **DB-side PageRank** — order edges on-disk, stream rank updates, instead of holding
  every node+edge in an in-memory `nx.MultiDiGraph`.
- **Incremental recompute** — re-scan only changed files (stat/diff), update rows,
  re-rank. This is the "scan ahead of time, agent reads disk-cache map" model, but the
  disk cache is now queryable.
- **`--full` becomes cheap** — the map is a query (`SELECT top-N by rank`), streamed
  to `--output` incrementally; no giant in-RAM output string.

`TAGS_CACHE` is already per-file diskcache, so the pivot mainly replaces the graph
construction + ranking I/O and the output assembly with on-disk storage.

## 3. Monorepo decomposition of core.py

`core.py` (2,008 lines) is the monolith. Break it into single-responsibility modules
so each goal below is independently testable.

Proposed layout:

```
core/
  pyproject.toml             # moved package entry points (tricorder + tricorder-mcp)
  __init__.py
  discovery.py               # discover_src_files, gitignore, compute_signature
  parser.py                  # tree-sitter parse + tag extraction (get_tags_raw)
  database.py                # the new on-disk DB: table DDL, insert/bulk, queries, schema version
  graph.py                   # edge building + on-disk PageRank (replaces in-memory nx walk)
  ranking.py                 # rank order, chat/mentioned boosts (from get_ranked_tags tail)
  render.py                  # to_tree / render_tree / to_mermaid (streams to file)
  report.py                  # FileReport + coverage accounting
  cache.py                   # existing per-file tags cache (diskcache) or absorbed into database.py
```

Every module keeps the current public function names under an adapter so
`tricorder.py`, `tricorder_server.py`, `plugins/tricorder/__init__.py`, and the bench
harness (`bench/`) keep working on `main` semantics until a module is migrated.

## 4. Achievable goals in dependency order

Each goal has an explicit **validation gate** that must pass before the next goal
starts. One goal at a time, no parallel agents.

### Goal 0 — Branch + spec + baseline (this commit)
- `dev/db-map` branch exists. Working spec committed + pushed to Gitea.
- **Validation gate:** `git branch --show-current` == `dev/db-map`; Gitea remote shows the
  branch; SPEC present; existing test suite baseline recorded (all passing on main).

### Goal 1 — Measure baseline on main (parity oracle)
- Record memory + output bytes on `main` for vaultwarden, go@6k, kotlin using
  `scripts/mem_probe.py`. This becomes the truth table any change must match (output) or
  beat (memory).
- **Validation gate:** a `SPEC_db_map` "baseline table" section populated with real
  numbers; the exact CLI+args recorded so parity can be re-run identically.

### Goal 2 — decompose core.py discovery + cache (no behavior change)
- Extract `discover_src_files`/gitignore/signature → `discovery.py`.
- Extract per-file tags cache → `cache.py` (or into `database.py` schema v0 that
  mirrors diskcache keys).
- **Validation gate:** full test suite passes; `calc_repo_map`-equivalent output byte-identical
  for vaultwarden + go@2.5k (run both before/after, diff stdout).

### Goal 3 — DB store (schema v1) writing per-file tags + refs ✅ DONE
- New `database.py`: sqlite table `tags(file, rel_file, line, name, kind)` +
  `refs(from_file, to_file, name)` + `meta(schema_version, root, signature)`.
- Wire the walk: after each file parse, bulk-insert tags/refs, drop AST.
- **Validation gate:** after scanning equals-BEFORE output and peak RSS during a
  kotlin scan drops materially vs baseline. **DB is now the DEFAULT execution
  path** (user-approved): `Tricorder(use_db=True)` default; CLI `--no-db` opts
  back to legacy nx, `--db-path` persists to a file instead of in-memory sqlite.

### Goal 4 — DB-side ranking ✅ DONE
- `database.py.pagerank()` — SQL power iteration on the `refs` table.
  Each iteration: dangling-mass sweep → incoming-rank join → rank update → convergence check.
  All computation on-disk; only the final rank dict (one float per file) is in RAM.
- Replaces the uniform-rank fallback in `_get_ranked_tags_db()`.
- Added `scipy>=1.13.0` + `numpy>=1.26.0` to `pyproject.toml` dependencies so the
  default path also runs real PageRank (previously scipy was missing → uniform fallback).
- **Validation gate:** DB path now produces real PageRank output (not uniform).
  Default path also runs real PageRank via scipy. Output differs from the old
  uniform baseline by design — the user explicitly approved breaking parity to
  get real ranking without in-memory graph blowup.

### Goal 5 — streamed `--full` output
- `--full` and `--output` stream from the rank query to the target file
  incrementally instead of assembling `tree_parts` string in RAM.
- **Validation gate:** output bytes identical to baseline `--full` for vaultwarden +
  go@2.5k; peak RSS during kotlin `--full` stays within a bounded cap.

### Goal 6 — incremental recompute (changed-files only)
- Diff files via signature/stat; re-scan only changed/new/deleted; update rows; re-rank.
- **Validation gate:** after editing one file in vaultwarden, map reflects the change
  without a full re-scan (verify by touching a file and checking the file is re-parsed
  while others are cache-hits); unit test over signature→affected rows.

### Goal 7 — merge to main (user decision)
- Run full bench + full test suite on `dev/db-map`; present results. User approves
  merge. **No merge happens without explicit approval.**

## 5. Non-goals (for now)
- Changing map semantics/format/tokens — parity with current output first.
- Replacing tree-sitter or grep-ast parsing.
- Async/parallel parsing (lane scope: single agent per goal).
- UI/CLI surface changes beyond the added `--db-path`/`--no-db` flags.

## 6. Validation harness
- `scripts/mem_probe.py` — memory/perf probe (exists).
- Reuse `bench/` for end-to-end confidence on the final merge.
- A parity script: run map on `main` and on `dev/db-map` for the same repo/flags,
  diff stdout byte-for-byte and compare peak RSS.

### Baseline commands (Goal 1 — the parity oracle)
All run from `D:/projects/tricorder` (`cd /d/projects/tricorder`), native `D:/` paths
for python (not MSYS `/d/...`). `rm -rf scripts/__pycache__` first if stale bytecode
throws `ModuleNotFoundError: resource`.

```
# vaultwarden
python scripts/mem_probe.py D:/projects/Tricorder-Testing-Repos/vaultwarden 20000 --max-files 100
# go @2500, and @6000
python scripts/mem_probe.py D:/projects/Tricorder-Testing-Repos/go 20000 --max-files 2500
python scripts/mem_probe.py D:/projects/Tricorder-Testing-Repos/go 20000 --max-files 6000
# go @2500 --full (output assembly cost)
python scripts/mem_probe.py D:/projects/Tricorder-Testing-Repos/go 20000 --max-files 2500 --full
# kotlin @1000 (SAFE cap only — 57k ballooned and OOM'd once)
python scripts/mem_probe.py D:/projects/Tricorder-Testing-Repos/kotlin 20000 --max-files 1000
```

Second positional arg = `map_tokens`. Record RSS after `get_ranked_tags` + traced peak
+ tags + seconds; for `--full` also chars/tokens. Any change on `dev/db-map` must
match output bytes here and beat RSS.