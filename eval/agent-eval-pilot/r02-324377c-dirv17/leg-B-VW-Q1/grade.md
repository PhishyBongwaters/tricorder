# Leg B-VW-Q1 — GRADE (Qwen model, grep-only baseline)

## Verdict: PASS

Ground truth (`validate_totp_code`,
`src/api/core/two_factor/authenticator.rs:115`) cited with line +
body details (totp_lite call :149, drift loop :143, replay guard
:152/:160), plus wrapper (`:101`), setup (`activate_authenticator`
:56), secret gen (`:22`), dep (`Cargo.toml:148`), module entry
(`mod.rs:27`). 15/15 calls (cap exhausted).

## Tokens (agent-visible result payloads, `meter_leg.py`, tiktoken cl100k)

| Step | Tokens | Note |
|---|---|---|
| 1 dir listing | 48 | root dirs |
| 2 totp grep (case-sens.) | 86 | 1 hit, config comment |
| 3 recurse *.rs | 1,471 | 62 files + two_factor dir found — the broad sweep |
| 4 read authenticator.rs | 569 | full 219 lines, answer in hand (call 7 of 15) |
| 5 read two_factor/mod.rs | 130 | routes/enum context |
| 6 protected_actions grep | 144 | email-OTP (not TOTP) — verification |
| 7 api/mod grep | 111 | struct context |
| 8 cargo grep | 56 | dep pin |
| **Total (metered)** | **2,615** | 8 artifacts |

## Metering gap (honest)

Transcript rows 15 calls but only 8 step artifacts saved — 7
intermediate outputs (greps at rows 4, 9–12, reads at 13–14) were
agent-visible but unmetered. True B cost > 2,615. The A/B gap below is
a floor, not a ceiling. Future legs: agent must save EVERY payload.

## A/B (VW-Q1)

| | Calls | Tokens |
|---|---|---|
| A (tricorder) | 5 | 634 |
| B (baseline) | 15 | 2,615+ (floor) |
| **A/B** | **0.33×** | **≤0.24×** |

B's cost drivers: the 1,471-token full-tree file listing (step 3) and
continuing 8 calls past the answer (verification reads). No ladder on
the B arm by design — thoroughness is the baseline's nature.
