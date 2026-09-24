# Leg B-Rails-Q1 attempt 1 — GRADE (Qwen baseline; commands via recall)

## Verdict: PASS — over cap (25 recalled calls vs 20 cap)

Ground truth (`has_many` at `associations.rb:1426`, builder chain,
`HasManyReflection:900`, proxy + `CollectionProxy`) cited with lines
and verified by reads. Deepest baseline leg of the series.

## Tokens (reproduced from recalled ranges, `meter.py`, tiktoken cl100k)

| Cmds | Step | Tokens |
|---|---|---|
| 1–2, 9, 11, 14–15, 18, 22 | listings + greps | 1,050 |
| 3–8, 10, 12–13, 16–17, 19–21, 23–25 | reads (14 files) | 17,815 |
| **Total** | | **18,865** |

## Compliance

- Baseline-only: clean (reads, listings, grep; zero tricorder).
- **Over cap**: 25 calls recalled vs 20 allowed. Reads include two
  comparison files (has_one, singular builder) outside the question.
- **Recall caveat**: command list recovered post-leg from the agent's
  memory (no live transcript); ranges cross-checked against the
  answer's citations. Treated as reported, not independently verified.
- Citation discipline clean; reads pre-sized (sizes checked first).

## A/B (Rails-Q1 pair, v1.3 series)

| Leg | Model | Verdict | Calls | Tokens |
|---|---|---|---|---|
| A-Rails-Q1 attempt 1 | Qwen | PASS | 7 | 30,201 as-run / 8,014 post-fix |
| B-Rails-Q1 attempt 1 | Qwen | PASS (over cap) | 25 | 18,865 |

Same model both sides (Qwen/Qwen) — the purest A/B of the series.
As-run the tricorder leg cost MORE (monster record); post-fix replay
(8,014) costs less than half the baseline. The baseline's 14 file reads
(17.8k) vs the tricorder leg's targeted 4 reads is the structural gap
the ladder exploits.
