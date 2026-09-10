# Proposal: Large-Repo Processing Speed

**Branch:** `dev/db-map`  
**Goal:** Make kotlin (57k files, ~14M tokens) and linux (66k files, ~50M tokens) tractable without 6-15h wall-clock. DB + incremental + resume are done; this is the speed tier on top.

## Current baseline (measured, `scripts/mem_probe.py`)

| Repo | Files | Tags | Time | Bottleneck |
|------|-------|------|------|------------|
| vaultwarden | 506 | 3.8k | 1.1s | trivial |
| go@2.5k | 2,500 | 56k | 7.7s | parse loop (single thread) |
| go@6k | 6,000 | 111k | 19s | parse + PageRank |
| kotlin@1k | 1,000 | 3.6k | 1.3s | parse |
| kotlin@57k | 57,161 | — | 6h+ then OOM | whole-repo walk + in-RAM graph (now DB, but still single-threaded) |
| linux | 66k | — | 3h+ (pre-index 1s with rg) | full walk without probe |

DB fix removed the OOM (flat walk + `file_state` resume), but **single-threaded parse** is now the wall. Tree-sitter is CPU-bound, Python GIL serializes it, and `sqlite` does one `INSERT` + `commit` per file.

## Ladder (ponytail)

### Tier 1 — Quick wins, no new deps, 1-2 days

1. **Batch DB transactions:** Group 100 files per `commit()` instead of per-file. WAL already on. Expected: 15-20% on go@2.5k (fewer fsyncs). `ponytail: 100-batch, tune if WAL grows`
2. **Skip empty/tiny files early:** Already `if not code.strip(): return` — keep, add `if len(code) < 50: fast-path` (many generated headers).
3. **Reuse parser per language:** Currently `get_parser(lang)` per file does a lookup; cache parsers in a dict keyed by `lang` (one `get_parser` per language, not per file). Expected: 5-10% on mixed repos.
4. **Pre-index default for huge repos:** If `discover_src_files` >10k and `pre_index` not set, auto-narrow via `rg` probe (opt-in via env `TRICORDER_AUTO_PREINDEX=1`). Keeps linux 1s path without user remembering flags.

*Tier 1 total estimate:* go@2.5k 7.7s → ~6s, kotlin 57k 6h → ~5h (still too long, but free).

### Tier 2 — Parallel parse, stdlib only, 3-5 days (recommended)

**ProcessPool, not threads:** Tree-sitter holds the GIL; `ThreadPoolExecutor` doesn't parallelize CPU. Use `concurrent.futures.ProcessPoolExecutor` (stdlib) with `os.cpu_count()` workers (8 on this box). DB stays in parent (WAL allows concurrent reads, but writes serialize).

Flow:

```
discover -> chunk files (e.g., 200) -> ProcessPool map(parse_file) -> parent inserts batch -> update file_state
```

- `parse_file(path)` is pure: `read_text` + `detect_lang` + `get_tags_raw` (which does `_parse_with_timeout`) → returns `[(rel, line, name, kind)]` or `[]`. No DB in workers.
- Parent loops over `as_completed`, does `db.insert_tags` + `db.set_file_state` in 100-file transactions.
- PageRank stays on-disk SQL (already parallel-safe, single-threaded SQL).
- `ponytail: ProcessPool, per-chunk batch. Ceiling: spawn overhead ~0.5s; upgrade to shared-memory DB if needed.`

Estimates (8 cores):

- go@2.5k: 7.7s → ~1.5-2s (4-5×)
- go@6k: 19s → ~4s
- kotlin@57k: 6h → ~50-70min (plus resume means second chunk is 1-dirty, not 6h again)
- vaultwarden unchanged (overhead dominates; skip pool if <200 files)

No new deps, no `async`, no `ray`. Pure stdlib.

### Tier 3 — Native / incremental deep (deferred, add when Tier 2 measurably falls short)

- **Native tree-sitter batch:** Use `tree-sitter`'s own parallel bindings or `pyo3` worker (not stdlib, new dep) — only if ProcessPool overhead is high on tiny files.
- **Incremental PageRank:** Don't recompute full PageRank after 1-file edit; do delta PageRank from `refs` diff. `ponytail: O(N) now, delta when N>50k and edit is single-file.`
- **Memory-mapped DB:** `PRAGMA mmap_size` for large refs table — only if PageRank I/O bounds.

Skipped for now.

## Resume integration

Tier 2 + existing resume (`missing = needed - stored`) makes kotlin tractable in chunks:

```bash
pre_scan.py --max-files 5000 kotlin  # chunk 1, 5000 files, ~6min
pre_scan.py --max-files 10000 kotlin  # chunk 2, adds 5000 missing (1-dirty each for existing, 5000 new) ~6min
# ... repeat to 57k, each chunk ~6min, not 6h restart
```

DB at `.tricorder/db/kotlin.db` accumulates.

## Validation gates (no 15h run)

- **Gate A:** `go@2.5k` wall-clock with Tier 2 vs single-thread, same output bytes (`to_tree` identical). Pass if >3× speedup and bytes identical.
- **Gate B:** `vaultwarden` 60-file incremental gate already passes; re-run after Tier 2 (1 dirty, 59 hits) still passes.
- **Gate C (deferred):** kotlin 5k chunk twice — second chunk reuses 5k (0 dirty) and adds next 5k (5000 dirty), total tags = sum, no wipe. Proves resume + parallel together.

## Risks

- ProcessPool on Windows needs `if __name__ == "__main__"` guard and `spawn` cost; mitigated by chunking 200 files per task.
- sqlite WAL write serialization in parent — not a bottleneck (inserts are 15% of time).
- Tree-sitter per-worker import overhead — mitigated by caching parsers per worker.

## Proposal ask

Approve **Tier 1 + Tier 2 (ProcessPool, stdlib only)**. That's ~1 week, no new deps, DB stays sole path, and kotlin/linux go from 6-15h to ~1h chunked. Tier 3 deferred until Tier 2 is measured.

File: `docs/PROPOSAL_large_repo_speed.md`
