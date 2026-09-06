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

| Repo | Files | Tags | RSS after walk | Traced peak |
|------|-------|------|----------------|-------------|
| vaultwarden | 100 | 219 | 47 MB | ~2 MB |
| go | 2,500 | 56,304 | 182 MB | 157 MB |
| go | 6,000 | 111,010 | 377 MB | 568 MB |
| kotlin | 57,161 | — | ballooned → killed | — |

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

### Goal 3 — DB store (schema v1) writing per-file tags + refs
- New `database.py`: sqlite table `tags(file, rel_file, line, name, kind)` +
  `refs(from_file, to_file, name)` + `meta(schema_version, root, signature)`.
- Wire the walk: after each file parse, bulk-insert tags/refs, drop AST.
- **Validation gate:** after scanning equals-BEFORE output (same map text as
  baseline) **and** peak RSS during a kotlin scan drops materially vs baseline
  (target >50% reduction). Add a `--db-path` + `--no-db` (in-memory) flag; default
  unchanged until this gate proves DB path.

### Goal 4 — DB-side ranking
- Replace in-memory `nx.MultiDiGraph` + PageRank with on-disk neighbor iteration.
  Sorting by rank stays in SQL query (`ORDER BY rank DESC LIMIT n`).
- **Validation gate:** rank order for vaultwarden/go@2.5k identical to baseline
  (same top-N tags, same order); memory for go@6k drops again (>50% from Goal 3).

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