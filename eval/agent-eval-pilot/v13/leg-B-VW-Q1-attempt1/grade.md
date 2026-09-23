# Leg B-VW-Q1 attempt 1 — GRADE

## Verdict: PASS

Ground truth (`validate_totp_code`, `authenticator.rs:115`) cited with
lines and verified by read — plus wrapper, enrollment caller, and the
login-flow dispatch (`identity.rs:827–828`) the A-leg never reached.
11/20 calls.

## Tokens (reproduced payloads, `meter.py`, tiktoken cl100k)

| Cmds | Step | Tokens |
|---|---|---|
| 1, 6, 7, 9 | listings + sizes | 225 |
| 3–5 | greps | 11,500 |
| 8, 10, 11 | reads | 2,242 |
| **Total** | | **13,967** |

## Compliance

- Baseline-only: clean. One harness error (bare grep, cmd 2), recovered
  immediately.
- Full-file read (cmd 8) was pre-sized (8KB/182 lines) — justified, not
  blind. Citation discipline clean.

## A/B (VW-Q1 pair, v1.3 series)

| Leg | Verdict | Calls | Tokens |
|---|---|---|---|
| A-VW-Q1 attempt 1 | PASS | 6 | 5,541 (post-fix replay) |
| B-VW-Q1 attempt 1 | PASS | 11 | 13,967 |

Both PASS, tricorder leg at 0.40× tokens and 0.55× calls. Note the
mirror: the baseline's broad `TwoFactor` grep (cmd 5, 10,231 tokens) is
the same junk-payload class as the tricorder incidents — undisciplined
patterns flood on both sides; the tricorder legs now have three stacked
defenses (exact-first, ×5 cap, strict-majority gate) while baseline has
only agent discipline.
