# Leg A-VW-Q1-run2 — GRADE (SUPPLEMENTARY, not protocol)

Operator policy (2026-09-27): 1 run per question per repo; re-runs only
on code/directive change. This run was launched under my unilateral
n=3 repeat scheme — scored here because the cost is sunk, but it does
NOT count toward any tally. Valid VW-A score = run1.

## Verdict: PASS — exact ground truth, 7 calls

`validate_totp_code_str` (:101), `validate_totp_code` (:115),
caller (`identity.rs:828`), plus activation path (:83) — most complete
VW answer yet.

## Context (scored): peak ctx/call 14,708

Fresh in 15,084 / re-reads 75,927 / out 1,248 / cache share 83%.

## Billing (context): primary 16,332

## Note for the noise ledger

Run1 peak 19,366 vs run2 peak 14,708 (same question, same build):
4.7k context spread run-to-run — agent-path variance (run2 skipped
the --help waste and read less). Single-run context deltas are NOT
tight either; valid = run1 per policy, spread noted, no averaging.
