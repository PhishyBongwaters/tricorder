# golang/go baseline-vs-branch: context-token comparison

**Date:** 2026-09-21 | **Worker:** golang/go comparison
**Baseline:** `438fd0b` (parent of branch, merge-base with origin/dev/db-map)
**Branch:** `5316c90` (fix/parallel-qualify tip)
**Repo:** golang/go @ `8002a0da`, 15,927 files, ~228 MB

## Method

Scripted navigation loop per question: `detect(kw1) → symbols(kw1) → detect(kw2) → symbols(kw2)` = **4 Tricorder MCP calls** per question. Each agent-visible response serialized to JSON exactly as the MCP stdio harness emits it, counted with tiktoken `cl100k_base`.

**Deviations from the 6-rung v3 loop (disclosed):**
1. **Detail rungs omitted (4 rungs, not 6).** `tricorder_detail` deadlocks building the whole-repo cross-file index on golang/go in this environment (both arms; 0% CPU, stuck in `do_wait`). The search phases (detect/symbols) are where the branch's response caps bite directly.
2. **3 questions, not 5** (G1/G3/G5; G2/G4 dropped for time).
3. **1 repetition.** Tools are deterministic: base G1=5,360 and G3=12,781 tokens reproduced bit-identically across two separate runs.
4. **In-process harness** (not subprocess-per-rung) with a harness-side in-memory memoization of `get_symbols` (which re-parses all 16k files per call with no in-tree cache; ~5 min/rung uncached). Memoization is keyed on (path, mtime, size) and returns bit-identical symbols — **measured token counts are unaffected**, only wall time.

Same budgets applied identically: tool defaults per arm (base: max_results=50, context_lines=2; tip: max_results=10, context_lines=1) — i.e., the actual user-facing defaults, consistent with v3 treatment. Separate `TRICORDER_CACHE_HOME` per arm; separate 1.4 GB scan DBs.

## Results (measured)

| Question | Baseline tokens | Branch tokens | Δ tokens | Δ % | Base calls | Branch calls | Base success | Branch success |
|---|---|---|---|---|---|---|---|---|
| G1 GC mark phase (`gcBgMarkWorker`) | 5,360 | 3,209 | **−2,151** | **−40.1%** | 4 | 4 | PASS 4/5 | PASS 3/5 |
| G3 channel ops (`chansend`) | 12,781 | 4,199 | **−8,582** | **−67.1%** | 4 | 4 | PASS 5/5 | PASS 5/5 |
| G5 compiler SSA (`buildssa`) | 1,547 | 1,343 | **−204** | **−13.2%** | 4 | 4 | PASS 5/5 | PASS 5/5 |
| **3-question session total** | **19,688** | **8,751** | **−10,937** | **−55.5%** | 12 | 12 | 3/3 | 3/3 |

Per-rung breakdown (tokens):

| | G1 base | G1 tip | G3 base | G3 tip | G5 base | G5 tip |
|---|---|---|---|---|---|---|
| detect1 | 1,857 | 969 (−48%) | 5,411 | 935 (−83%) | 391 | 317 (−19%) |
| symbols1 | 352 | 352 (0%) | 1,964 | 1,136 (−42%) | 175 | 175 (0%) |
| detect2 | 2,350 | 1,087 (−54%) | 4,101 | 1,009 (−75%) | 693 | 563 (−19%) |
| symbols2 | 801 | 801 (0%) | 1,305 | 1,119 (−14%) | 288 | 288 (0%) |

**Where the savings come from:** the `detect` rungs dominate the delta (G3 detect1 −83%, detect2 −75%) — the branch's `max_results` 50→10 cap directly truncates the long tail of identifier matches on a 16k-file repo. `symbols` rungs save less; when a query returns ≤10 symbols even on baseline (G1, G5), the cap doesn't bite and tokens are identical (0% delta), confirming the cap is the mechanism, not a ranking change. G5's small delta (−13%) is because `buildssa`/`NewConfig` are rare identifiers with few matches under either cap.

## Context-window analysis (32k / 64k / 128k)

3-question session totals: **baseline 19,688 vs branch 8,751 tokens**.

| Window | Baseline 19,688 | Branch 8,751 |
|---|---|---|
| 32k | fits at **61%** of window | fits at **27%** of window |
| 64k | fits at 31% | fits at 14% |
| 128k | fits at 15% | fits at 7% |

Neither overflows 32k on 3 questions, so no "baseline exceeds while branch fits" flag fires at this question count. But the branch leaves **2.25× more headroom**: baseline consumes nearly two-thirds of a 32k window on just 3 lookups, leaving ~12k tokens for the agent's own reasoning, follow-up tool calls, and file reads; the branch leaves ~23k. On a realistic longer session (more questions, file reads, edits), the baseline's 2.25× burn rate is what pushes a 32k-window local model into overflow while the branch stays comfortable — the same pattern the Vaultwarden leg showed (−66.5%, baseline session overflowed 32k).

Per-question worst case: G3 alone is 12,781 (base) vs 4,199 (tip) — a single channel-lookup question costs 40% of a 32k window on baseline vs 13% on branch.

## Artifacts

- Base: `~/workspace/comparisons/results-go/20260921T221900Z-go-base-ds4/` (steps.json per rung, grade.json, results.csv)
- Tip: `~/workspace/comparisons/results-go/20260921T221013Z-go-tip-ds4/`
- Harness: `~/workspace/comparisons/run_go_eval_ds4.py` (imports `install_symbols_cache`, `count_tokens` from `run_go_eval_fast.py`)
- 3-question corpus: `~/workspace/comparisons/tasks_go_3.json`

## Notes for the parent

- The dedicated baseline worktree `~/workspace/comparisons/tricorder-baseline-go` (at 438fd0b) still exists; remove with `git -C ~/workspace/tricorder worktree remove ~/workspace/comparisons/tricorder-baseline-go` when all workers are done.
- The `detail` deadlock is worth flagging to the user separately: on golang/go, `tricorder_detail`'s cross-file index build hangs (both arms). It worked on smaller repos (fastapi, vaultwarden). This is a scalability bug independent of the branch.
- Go clone `~/workspace/comparisons/go` left untouched (read-only as required).
