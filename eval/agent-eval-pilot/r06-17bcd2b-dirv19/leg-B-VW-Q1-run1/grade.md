# Leg B-VW-Q1-run1 — GRADE (operator model, harness-metered, baseline)

## Verdict: PASS — complete, 3 calls

Textbook baseline: one grep (`totp`), one full-file read
(`authenticator.rs`), one caller window (`identity.rs` 810–839).
Ground truth exact with body evidence (BASE32 :124, drift loop
:143–149, replay guard :152, save :160–161).

## Context (scored): peak ctx/call 13,340

Fresh in 13,513 / re-reads 30,163 / out 540 / cache share 69%.

## Billing (context): primary 14,053
