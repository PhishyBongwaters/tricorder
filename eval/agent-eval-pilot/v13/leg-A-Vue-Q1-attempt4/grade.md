# Leg A-Vue-Q1 attempt 4 — GRADE (Qwen model)

## Verdict: PASS — **v1.6 compliant, v1.5 minor exceedance (one chained pair)**

Correct answer, citations ±few (drift, not exact). 8/15 calls, 5,068
tokens — cheapest compliant-era leg on any repo.

## Tokens

| Step | Tokens | Note |
|---|---|---|
| probe | 64 | held |
| MAP | 0 | skipped (3rd leg running) |
| detect 1 × ("reactive", 5) | 513 | NL-ish first query, hit anyway |
| reads 6 × (100–127 ln) | 4,491 | one chained pair |
| **Total** | **5,068** | **0.79× att.3, 0.56× B** |

## Compliance

- v1.6 obeyed; amended v1.3 obeyed (single first pass at 5).
- Deviations, all minor: first query `"reactive"` is concept-NL, not an
  exact guess (v1.3 letter bent, goal met — 513 tok hit); watcher chained
  pair without inter grep (v1.5 recurring); index second window 127 lines
  grep-less (7 over cap).
- Literal adherence wobbles while tokens fall monotonic across attempts
  (10,177 → 9,404 → 6,384 → 5,068): the directive is better judged by its
  numbers than its letter — per the RUNLOG grading principle.

## Attempts 1 → 4

| | Att.1 | Att.2 | Att.3 (v1.6) | Att.4 (frozen) |
|---|---|---|---|---|
| Calls | 13 | 15 | 11 | 8 |
| Tokens | 10,177 | 9,404 | 6,384 | 5,068 |
| A/B | 1.13× | 1.04× | 0.71× | **0.56×** |

## Model Tracking

| Leg | Model | Provider |
|---|---|---|
| A-Vue-Q1 att.1–4 | **Qwen** | **llamacpp** |
| A-Elixir-Q1 att.1–4, B-Elixir-Q1, B-Vue-Q1 | Qwen | llamacpp |
| A-VW-Q3/Q4, A-G1-Qwen, A-Rails-Q1, B-Rails-Q1 | Qwen | llamacpp |
| All other v1.3 A-legs | Nemotron | opencode |
