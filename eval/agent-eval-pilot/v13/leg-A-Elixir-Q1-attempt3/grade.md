# Leg A-Elixir-Q1 attempt 3 — GRADE (Qwen model)

## Verdict: PASS — **v1.5 NON-compliant (chained pair + over-ceiling windows)**

Correct answer, citations verifier-confirmed. 12/15 calls, 10,359 tokens —
statistically identical to attempt 2 (14 calls, 10,264), but the SHAPE
regressed to attempt-1-style walking in smaller windows.

## Tokens

| Step | Tokens | Note |
|---|---|---|
| MAP 2048 | 2,079 | noise, unchanged |
| detect "GenServer" (10) | 982 | unchanged |
| reads 8 × (20–150 ln) | 7,057 | 68% of leg |
| greps 2 × | 241 | post-hoc, not pre-justifying |
| **Total** | **10,359** | ≈ att.2 (10,264) |

## Compliance

- **Chained doc pair:** steps 3–4 (1–120 + 121–240) with no locating grep
  between — the exact pattern v1.5 forbids.
- **Over-ceiling windows:** 577–699 (123), 700–849 (150), 891–1025 (135).
- **8 windows, 1 file, 2 greps:** step-5 grep arguably justifies 6–7, step-11
  justifies 12; windows 3–4 and 8–10 had no grep justification. Greps were
  used as locators after the fact, not as gatekeepers before second windows.
- v1.5 as written did NOT change behavior: the agent read the rule and
  walked anyway. Data point against rule-based ceilings without enforcement —
  the per-call 120 cap (v1.4) held mechanically in att.2/vue; the
  one-window gate (v1.5) did not survive contact.

## Attempts 1 → 2 → 3

| | Att.1 (v1–v1.3) | Att.2 (v1–v1.4) | Att.3 (v1–v1.5) |
|---|---|---|---|
| Calls | 9 | 14 | 12 |
| Tokens | 17,357 | 10,264 | 10,359 |
| Shape | 5 × 200–300 whole walk | bodies + 4 greps | 8 × 20–150 walk |
| Compliance | FAIL | PASS | NON-compliant (v1.5) |

Tokens flat att.2→att.3; discipline regressed. v1.4 (mechanical cap) bites,
v1.5 (behavioral gate) doesn't — at least not on first exposure.

## Model Tracking

| Leg | Model | Provider |
|---|---|---|
| A-Elixir-Q1 att.1/2/3 | **Qwen** | **llamacpp** |
| A-Vue-Q1, B-Elixir-Q1 | Qwen | llamacpp |
| A-VW-Q3/Q4, A-G1-Qwen, A-Rails-Q1, B-Rails-Q1 | Qwen | llamacpp |
| All other v1.3 A-legs | Nemotron | opencode |
