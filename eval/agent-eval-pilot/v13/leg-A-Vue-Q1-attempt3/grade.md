# Leg A-Vue-Q1 attempt 3 — GRADE (Qwen model)

## Verdict: PASS — **v1.6 compliant, v1.5 minor exceedance (one chained pair)**

Correct answer, exact citations. 11/15 calls, 6,384 tokens — best
A-number in the series on a small repo, and the pair flips.

## Tokens

| Step | Tokens | Note |
|---|---|---|
| probe | 64 | scale calibration |
| MAP | 0 | SKIPPED per v1.6 (saves 2,061) |
| detects 3 × (10/5/10) | 2,445 | two at 10 cost ~950 each |
| symbols observe | 504 | gatekeeper for windows 10–11 |
| reads 6 × (25–123 ln) | 3,371 | one chained pair |
| **Total** | **6,384** | **0.63× att.1, 0.71× B** |

## Compliance

- v1.6 obeyed exactly: probe → one exact detect names file → MAP skipped.
- v1.5: steps 9→10→11 are the compliant pattern (symbols gate, two
  justified windows); steps 7→8 (watcher chained pair, no inter grep) are
  the recurring exceedance. Read 128–250 runs 3 lines over the 120 cap —
  trivial.
- Detects at --max-results 10 (steps 2, 6) instead of v1.3's 5: exact
  guesses, all hits, but ~950 tok each vs ~500 — half the MAP savings
  went back here. Next refinement lives in detect caps, not reads.

## Attempts 1 → 2 → 3

| | Att.1 (v1–v1.4) | Att.2 (v1–v1.5) | Att.3 (v1–v1.6) |
|---|---|---|---|
| Calls | 13 | 15 | 11 |
| Tokens | 10,177 | 9,404 | 6,384 (0.63×/0.68×) |
| A/B | 1.13× (loss) | 1.04× (loss) | **0.71× (win)** |
| MAP | 2,061 blind | 2,061 blind | skipped |

v1.6 flips the only losing pair in the series. Theory confirmed: on
small repos the fixed MAP price dominates, and stopping payment beats
any read discipline.

## Model Tracking

| Leg | Model | Provider |
|---|---|---|
| A-Vue-Q1 att.1/2/3 | **Qwen** | **llamacpp** |
| A-Elixir-Q1 att.1/2/3, B-Elixir-Q1, B-Vue-Q1 | Qwen | llamacpp |
| A-VW-Q3/Q4, A-G1-Qwen, A-Rails-Q1, B-Rails-Q1 | Qwen | llamacpp |
| All other v1.3 A-legs | Nemotron | opencode |
