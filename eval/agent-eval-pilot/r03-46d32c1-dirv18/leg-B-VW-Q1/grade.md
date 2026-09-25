# Leg B-VW-Q1 — GRADE (operator model, harness-metered)

## Verdict: PASS — minimal baseline, 3 substantive calls

Ground truth (`validate_totp_code`,
`src/api/core/two_factor/authenticator.rs:115`) cited exact with body
evidence; wrapper (`:101`), login call-site (`identity.rs:828`), and
enrollment call-site (`:83`) verified. No tricorder contact.

## Tokens (harness session truth, provider-native units)

Session `ses_f26912729ffeiPLMwJVeDGoh7b` (muse-spark):
in=28,476 / out=724 / reasoning=255 / cache_read=38,724.
Primary (in+out): **29,200**.

## Ladder audit (from session log)

Prompt read → one whole-repo grep `totp` → full read
`authenticator.rs` → full read `identity.rs` → answer. No repeats.
Note: both reads were FULL files (no line limits) — payload-heavy
baseline habit; the cost shows in truth (28k in on 4 tools).

## A/B (VW-Q1, r03 — same model, same question, same build)

| | Calls (substantive) | Truth in+out |
|---|---|---|
| A (tricorder) | 7 | 14,743 |
| B (baseline) | 3 | 29,200 |
| **A/B** | | **0.50×** |
