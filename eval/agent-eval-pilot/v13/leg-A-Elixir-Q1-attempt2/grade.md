# Leg A-Elixir-Q1 attempt 2 — GRADE (Qwen model)

## Verdict: PASS — **ladder compliant (v1.4)**

Same question, same model as attempt 1, run under v1–v1.4. Correct answer
with EXACT file+line+symbol citations (all verifier-confirmed). 14/15 calls.

## Tokens

| Step | Tokens | Note |
|---|---|---|
| MAP 2048 | 2,079 | noise, unchanged |
| detect "GenServer" (10) | 982 | unchanged |
| reads 8 × ≤120 lines | 7,067 | grep-guided bodies/docs |
| in-file greps 4 × | 290 | callback/def locators |
| **Total** | **10,264** | **−41% vs attempt 1 (17,357)** |

## Compliance

- All reads ≤120 lines, one logical section each; grep-guided targeting
  (steps 5/9/11/13) replaced blind sequential walking. No whole-file walk.
- Minor notes (no fail): SYMBOLS rung skipped (MAP → DETECT → READ/grep);
  in-file `Select-String` greps are B-style tools used inside an A-leg but
  stayed in-repo, in-file, and counted against the cap — rung-4-adjacent,
  acceptable. Steps 3–4 (doc windows 1–240) precede targeting; oriented,
  not answered, then narrowed.
- v1.4 test outcome: **the ceiling held.** Attempt 1's 73%-in-reads
  collapsed to targeted bodies; citations went from approximate (~lines)
  to exact.

## Attempt 1 → 2 (fix effect)

| | Attempt 1 (v1–v1.3) | Attempt 2 (v1–v1.4) |
|---|---|---|
| Calls | 9 | 14 |
| Tokens | 17,357 | 10,264 (0.59×) |
| Reads | 5 × 200–300 lines, whole file | 8 × ≤120 lines + 4 greps |
| Citations | approximate | exact, verified |
| Compliance | FAIL (rung-4 overbreadth) | PASS |

More calls, fewer tokens — the tradeoff v1.4 was designed to force.

## Model Tracking

| Leg | Model | Provider |
|---|---|---|
| A-Elixir-Q1 att.1/att.2 | **Qwen** | **llamacpp** |
| A-VW-Q3/Q4, A-G1-Qwen, A-Rails-Q1 | Qwen | llamacpp |
| All other v1.3 A-legs | Nemotron | opencode |
