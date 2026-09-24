# Leg A-Vue-Q1 attempt 2 — GRADE (Qwen model)

## Verdict: PASS — **v1.5 minor exceedance (same chained class as att.1)**

Correct answer, citations ±few lines (close, not exact — minor drift vs
att.1's exactness). 15/15 calls (at cap), 9,404 tokens — best A-number on
either new repo.

## Tokens

| Step | Tokens | Note |
|---|---|---|
| MAP 2048 | 2,061 | types-only noise, unchanged |
| detects 5 × (max-res 5) | 2,449 | all exact-first hits |
| reads 9 × (25–127 ln) | 5,329 | incl. 2 chained pairs |
| grep 1 × | 23 | the one compliant gatekeeper |
| **Total** | **9,404** | **0.92× att.1 (10,177)** |

## Compliance

- Chained pairs recur: watcher.ts 1–120 + 121–240, scheduler.ts 1–120 +
  121–240 — no locating grep between windows. Index.ts second window
  (1–127, 7 lines over cap) also grep-less.
- ONE compliant v1.5 sequence exists (steps 13→14→15: orient, grep
  `observe(`, read 155–180) — the agent CAN do the pattern; it doesn't
  generalize it.
- 4 detect wordings vs rung-2 "1–2 max" (att.1 also used 4) — minor,
  all capped at 5, all hits. Rung-2 wording budget may itself need a look.
- v1.5 twice non-decisive (Elixir att.3 outright, Vue att.2 partial):
  behavioral gates don't survive contact; mechanical caps (v1.4) do.

## Attempts 1 → 2

| | Att.1 (v1–v1.4) | Att.2 (v1–v1.5) |
|---|---|---|
| Calls | 13 | 15 (cap) |
| Tokens | 10,177 | 9,404 (0.92×) |
| Chained pairs | 2 (+watcher-240?) | 2 |
| Grep-justified 2nd window | 0 | 1 (state.ts) |
| Citations | exact | ±few lines |

## Model Tracking

| Leg | Model | Provider |
|---|---|---|
| A-Vue-Q1 att.1/att.2 | **Qwen** | **llamacpp** |
| A-Elixir-Q1 att.1/2/3, B-Elixir-Q1, B-Vue-Q1 | Qwen | llamacpp |
| A-VW-Q3/Q4, A-G1-Qwen, A-Rails-Q1, B-Rails-Q1 | Qwen | llamacpp |
| All other v1.3 A-legs | Nemotron | opencode |
