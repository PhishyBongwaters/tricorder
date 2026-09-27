# Leg A-VW-Q1-run1 — GRADE (operator model, harness-metered, v1.9, r06)

## Verdict: PASS — exact ground truth, 9 calls

`validate_totp_code` (`authenticator.rs:115`) with body evidence,
wrapper (`:101`) and caller (`identity.rs:828`) — matches the
established ground truth file+line+symbol. Third leg in five to burn
a call on `--help` (call 7): pattern confirmed, directive should pin
the flag set or forbid --help.

## Context (scored — what the window actually holds)

Peak ctx/call: **19,366**. Fresh in 32,360 / re-reads 94,442 /
out 1,364 / cache share 74%.

## Billing (context, never verdict)

Primary (in+out): 33,724. Input runs hot here (32k fresh on only 9
calls — small-repo MAP/symbols payloads dominate, not misses).

## Ladder audit (from session log, 8 shell + 1 read)

init → probe → smart-map `"totp"` (identifier rung 1; NO exact
`totp` tag → MAP fallthrough as written, T2 verified live) →
detect `verify_totp` → detect `totp` (exact-first, 2 wordings) →
symbols `validate_totp_code_str` → `--help` (waste) → read 85–144 →
`--mention validate_totp_code` → answer. Guards untriggered.
Ladder worked as designed: skip missed honestly, rungs 2–4 closed it.
