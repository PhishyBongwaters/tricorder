# Comparison runs — 2026-09-21

**Canonical savings numbers.** This is the single source of truth for all
token-savings claims in the docs, until a newer committed run supersedes it.
Measured at tip of `fix/parallel-qualify` (current pipeline), response-payload
tokens via tiktoken `cl100k_base` — not estimates.

Baseline-vs-branch (tip of `fix/parallel-qualify`) repo comparison runs
measuring **context tokens used** per query on large repos.

Goal: quantify context savings for 16GB VRAM local AI models working on
code repos — i.e. how much less context a navigation session burns, and
whether sessions that overflow a small window (e.g. 32k) fit with the
branch.

## Methodology

- Same frozen question corpus on both variants (see `corpora/`).
- Each question is graded against ground truth: expected file, line, and
  symbol names.
- Token counts are **measured from actual payloads** (tiktoken
  `cl100k_base`), never estimated.
- Per question: `detect` (find the symbol) → `symbols` (list candidates)
  → `detail` (fetch the definition).
- The initial repo scan is a sunk cost reported separately; a realistic
  short session = scan + questions.

## Results

### Vaultwarden (Rust, medium-large) — complete

Branch used **8,987 tokens vs baseline 26,818** across 4 questions
(−17,831 tokens, **−66.5%**). Answer success: 4/4 on both.

| step | baseline | branch |
|---|---|---|
| scan (sunk) | 10,670 | 1,783 |
| Q1 totp code | 2,402 | 2,246 |
| Q2 admin token | 2,495 | 2,069 |
| Q3 collection permissions | 17,506 | 2,417 |
| Q4 cipher update notification | 4,415 | 2,255 |
| **questions total** | **26,818** | **8,987** |
| **session (scan + questions)** | **37,488** | **10,770** |

Headline for 16GB VRAM local models: a full Vaultwarden session is
37,488 tokens on baseline — **over a 32k window** — and 10,770 with the
branch, comfortably inside. The biggest single driver is Q3, where the
baseline's `detect` step burned 10,714 tokens vs 1,084 on the branch.

### Go (golang/go, 16k files) — complete, 3 questions

Branch used **8,751 tokens vs baseline 19,688** (−10,937 tokens,
**−55.5%**). Answer success: 3/3 on both.

| question | baseline | branch |
|---|---|---|
| G1 GC mark phase | 5,360 | 3,209 |
| G3 Channel ops | 12,781 | 4,199 |
| G5 Compiler SSA | 1,547 | 1,343 |
| **total** | **19,688** | **8,751** |

Raw per-rung data in `results-go/20260921T221900Z-go-base-ds4/` and
`results-go/20260921T221013Z-go-tip-ds4/`; narrative in
`results-go/go-final-report.md`. 4 rungs/question with harness-side
memoization of `get_symbols` (verified bit-identical output) to avoid
hours of re-parsing.

### Swift (swiftlang/swift, 32,805 files; indexed subset `lib`+`include`, 2,324 files) — complete, 5 questions

Branch used **9,789 tokens vs baseline 69,875** (−60,086 tokens,
**−86.0%**). Answer success: 5/5 baseline, 4/5 branch — Q4 is the only
accuracy regression across all 12 questions (see Caveats).

| question | baseline | branch |
|---|---|---|
| Q1 Function-call type checking | 27,276 | 2,242 |
| Q2 SIL inliner cost model | 2,509 | 1,411 |
| Q3 String interpolation | 1,859 | 1,877 |
| Q4 Expression parser | 18,809 | 2,191 |
| Q5 Qualified name lookup | 19,422 | 2,068 |
| **total** | **69,875** | **9,789** |

Shallow clone used due to repo size. v3's 6-rung loop times out on
32k-file trees, so both arms ran an adapted 2-rung method (`detect`
with the server's huge-repo fast path) over the indexed `lib`+`include`
subset. Per-question payloads in `results-swift/results-20260921T204525Z/`.

### Combined

All three repos: baseline **116,381 → branch 27,527** tokens
(−88,854, **−76.3%**).

Headline for 16GB VRAM local models:
- Vaultwarden session (scan + 2 heavy questions): **32,591 baseline
  overflows a 32k window; branch 6,455** fits with 80% headroom.
- Go 3-question session: **61% of 32k** baseline vs **27%** branch.
- Swift 5-question session: **69,875 baseline overflows 32k AND 64k;
  branch 9,789** fits comfortably. Both fit 128k.

## Caveats

- Single rep per variant; scripted policies deterministic (Go verified
  bit-identical reproduction across two runs).
- Vaultwarden used the MCP tool surface on both arms (baseline CLI
  lacks `--detect`/`--symbols`; neither CLI has `--detail`).
- Path strings (`vw-tip`/`vw-base`, length-identical) verified not to
  affect token counts.
- **Swift Q4 accuracy regression:** the branch cited
  `Parser::parseExpr` in the header but missed
  `lib/Parse/ParseExpr.cpp` — a precision/recall tradeoff from
  stricter qualify matching. Only regression in 12 questions.
  *(Follow-up 2026-09-22, commit `090456e`: fixed — detect result
  tiers now interleave hits per file (round-robin) before applying
  the result cap, so many same-name hits in one header can no longer
  crowd definition sites in other files out of the budget. Verified
  with a red→green regression test; not yet re-measured on the full
  Swift corpus.)*
- **Large-repo `detail` slowness, investigated (both arms):** the
  original report described `tricorder_detail` as deadlocking while
  building the whole-repo cross-file index (0% CPU, stuck in
  `do_wait`) on 16k-file repos. Follow-up reproduction on branch
  `090456e` with the 11.7k-file Go corpus could NOT reproduce any
  hang: the cross-file index built in 221s with steady progress, and
  a cold parallel DB build finished `EXIT=0` in ~12.5 min with a
  valid DB (12,911 files / 1,398,161 tags / 12,278,752 refs). The
  0%-CPU/`do_wait` signature matches the *parent* harness process
  waiting on a healthy 10–15-minute child, not a deadlock — first
  `detail` on a huge repo is slow (then disk-cached), not stuck.
  No code change was warranted. Repro script and logs:
  `~/workspace/deadlock-repro/` (outside the repo).

## Layout

- `corpora/` — frozen question corpora with ground truth
  (`vw_corpus.json`, `tasks_go.json`, `tasks_go_3.json`).
- `scripts/` — the exact scripts that ran the comparisons, plus the
  question-probing and grading helpers.
- `runs/` — raw per-run JSON records (variant, scan token counts,
  per-step payloads with token counts) for Vaultwarden.
- `results-go/` — Go final report plus raw per-rung data for both
  variants.
- `results-swift/` — Swift results (per-question CSV/Markdown, prescan
  config, per-question payload artifacts).
- `logs/` — stage logs from the Swift and Go runs.

## Excluded (not portable)

- Cloned repos (`go/`, `swift/`, `vw-base/`, `vw-tip/`) and tricorder
  checkouts used as variants.
- Built SQLite index DBs (multi-GB for Go) and cache dirs.
- `/tmp` scratch. Everything needed to reproduce the numbers is above;
  re-cloning the target repos at the recorded revisions and re-running
  `scripts/` reproduces `runs/`.
