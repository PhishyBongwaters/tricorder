# Leg A-VW-Q2 attempt 3 — GRADE (Qwen model)

## Verdict: PASS — **NON-compliant (cap overrun 19>15 + chained walk)**

Exact ground-truth citation, no integrity flag. But 19 ops against a 15
cap, and admin.rs 1–310 walked in 4 chained windows.

## Tokens

| Step | Tokens | Note |
|---|---|---|
| probe | 64 | held |
| MAP | 0 | skipped (5th leg running) |
| detects 1 × + symbols 3 × | 1,973 | capped, all hits |
| T1 (jQuery junk, 2nd leg running) | 2,040 | 26% of leg, unread |
| reads 9 × + greps 4 × | 3,866 | walked 1–310 + JWT windows |
| **Total** | **7,943** | |

## Compliance

- Cap overrun is the headliner: 19 ops claimed as 15. Same read-counting
  slip as VW-Q1 att.2 ("reads don't count"), now load-bearing — without
  it the leg is 6 CLI calls and comfortably in cap. Agents systematically
  undercount shell/file ops; the harness counts every invocation.
- Chained 1–310 walk (v1.4/v1.5 fail class) + T1 junk (VW-Q1 att.2 class).
- The retry itself answers the loop diagnosis: fresh server + verbatim
  prompt = clean completion. Loop cause was server fatigue and/or wrapper
  garnish, not the directive or the question.

## VW-Q2 across attempts

| | Att.1/2 (Nemotron) | Att.3 (Qwen, frozen) |
|---|---|---|
| Calls | 16 / 5 | 19 (claimed 15) |
| Tokens | ~12k / ~15k | 7,943 |
| Best A | — | 7,943 vs B att.1 (5 calls, 18,721): **0.42×** |

Qwen halves the Nemotron numbers even while overrunning the cap. B-leg
Qwen re-run still owed for a current pair ratio.

## Model Tracking

| Leg | Model | Provider |
|---|---|---|
| A-VW-Q2 att.3 | **Qwen** | **llamacpp** |
| A-VW-Q2 att.1/2 | Nemotron | opencode |
| Rest of Qwen-everywhere program | Qwen | llamacpp |
