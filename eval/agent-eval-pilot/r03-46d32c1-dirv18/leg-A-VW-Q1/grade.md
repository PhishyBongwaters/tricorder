# Leg A-VW-Q1 — GRADE (operator model, harness-metered)

## Verdict: PASS — fully compliant, 7 calls

Ground truth (`validate_totp_code`,
`src/api/core/two_factor/authenticator.rs:115`) cited exact with body
evidence (BASE32 :124, totp_custom :149, replay guard :152); wrapper
(`:101`) and caller (`identity.rs:828`) verified. Answer complete.

## Tokens (harness session truth, provider-native units)

Session `ses_f2692da5affemV4XzikqhxeKcb` (muse-spark):
in=13,418 / out=1,325 / reasoning=494 / cache_read=84,601.
Primary (in+out): **14,743**.

## Ladder audit (from session log)

init → probe → smart-map (full NL question as query) → detect
`verify_totp` → detect `totp` → symbols `validate_totp_code_str` →
read 80–159 → answer. Eval guards untriggered (no repeats, steady
progress). v1.7/v1.8 smart-map path followed.

## Comparison (VW-Q1 A-arm, harness truth throughout)

| Leg | Calls | Truth in+out | Note |
|---|---|---|---|
| v13 A-Q1-att1 | 7 | 34,323 | MAP rung paid blind (2,040) |
| r03 A-Q1 | 7 | 14,743 | smart-map declined MAP on miss |
