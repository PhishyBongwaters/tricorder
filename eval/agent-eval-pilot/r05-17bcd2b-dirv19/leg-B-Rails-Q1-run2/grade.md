# Leg B-Rails-Q1-run2 — GRADE (operator model, harness-metered, baseline)

## Verdict: PASS — complete, 13 calls (agent self-reported 12)

Full pipeline + roster with line cites, same ground as B-run1.
Second self-report mismatch in two legs (13 harness vs 12 claimed) —
harness rows meter, never claims.

## Tokens (harness session truth, provider-native units)

Session `ses_f22137cf3ffedRI6UhYRMaly3y` (muse-spark):
in=23,476 / out=2,119 / reasoning=643 / cache_read=139,498.
Primary (in+out): **25,595**.

## Context differential (what the window actually holds)

Fresh in 23,476 / re-reads 139,498 / out 2,119 / peak ctx 22,964 /
cache share 86%.

## Running tally (Rails B)

| Run | Calls | Truth in+out | Peak ctx | Note |
|---|---|---|---|---|
| run1 (r04) | 15 | 25,466 | — (backfill pending) | at cap |
| run2 | 13 | 25,595 | 22,964 | |
| mean (n=2) | 14 | 25,531 | — | spread 129: baseline stable |
