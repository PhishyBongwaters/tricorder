# Comparison runs — 2026-09-21

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

### Go (golang/go) — in progress at commit time

Corpora and eval script committed (`corpora/tasks_go.json`,
`corpora/tasks_go_3.json`, `scripts/run_go_eval.py`); results to follow
in a follow-up commit.

### Swift (swiftlang/swift) — in progress at commit time

Eval script committed (`scripts/swift_eval.py`); shallow clone used due
to repo size. Prescan stage logs in `logs/`. Results to follow.

## Layout

- `corpora/` — frozen question corpora with ground truth
  (`vw_corpus.json`, `tasks_go.json`, `tasks_go_3.json`).
- `scripts/` — the exact scripts that ran the comparisons, plus the
  question-probing and grading helpers.
- `runs/` — raw per-run JSON records (variant, scan token counts,
  per-step payloads with token counts) for Vaultwarden.
- `logs/` — stage logs from the Swift and Go runs.

## Excluded (not portable)

- Cloned repos (`go/`, `swift/`, `vw-base/`, `vw-tip/`) and tricorder
  checkouts used as variants.
- Built SQLite index DBs (multi-GB for Go) and cache dirs.
- `/tmp` scratch. Everything needed to reproduce the numbers is above;
  re-cloning the target repos at the recorded revisions and re-running
  `scripts/` reproduces `runs/`.
