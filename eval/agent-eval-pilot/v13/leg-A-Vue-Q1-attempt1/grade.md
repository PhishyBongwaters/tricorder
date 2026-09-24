# Leg A-Vue-Q1 attempt 1 — GRADE (Qwen model)

## Verdict: PASS — **compliant with minor v1.4 exceedance (chained pairs)**

Correct answer, exact citations throughout (defineReactive :128, Dep :31,
Watcher :41, observe :104, initData state.ts:164 — all verified). 13/15 calls.

## Tokens

| Step | Tokens | Note |
|---|---|---|
| MAP 2048 | 2,061 | types only, impl absent |
| detects 4 × (max-res 5) | 1,948 | 458–508 each, all exact-first hits |
| reads 8 × | 6,168 | bodies + two chained pairs |
| **Total** | **10,177** | reads = 61% |

## Compliance

- Exact-first obeyed on all 4 detects, capped at 5 per v1.3; `--format json`
  throughout; in-repo; rung 0 skipped; no `--db-path`.
- **Minor exceedance:** state.ts 1–200 and scheduler.ts 1–199 were each
  covered in two chained ≤120-line windows — the v1.4-chained pattern at
  small-file scale (200-line files, not 1,376). Every per-call limit held
  (120/120/120/80/120/80/120/80); windows targeted already-identified
  symbols (initData, queueWatcher); agent stopped at the answer. Recorded
  as exceedance, not fail: no blind walking, no cap breach.
- Watcher.ts 1–240 single coverage unclear in recall (limit reported 120,
  coverage 240) — flagged unverified, same class.
- **Series signal:** v1.4's per-call cap holds (2/2 legs); chaining persists
  for ≤200-line files. Possible future rule (NOT this series): one window
  per file unless a grep justifies the second. Elixir att.2 needed no
  second windows thanks to in-file greps — the greps ARE the substitute.

## Model Tracking

| Leg | Model | Provider |
|---|---|---|
| A-Vue-Q1 | **Qwen** | **llamacpp** |
| A-Elixir-Q1 att.1/att.2, B-Elixir-Q1 | Qwen | llamacpp |
| A-VW-Q3/Q4, A-G1-Qwen, A-Rails-Q1, B-Rails-Q1 | Qwen | llamacpp |
| All other v1.3 A-legs | Nemotron | opencode |
