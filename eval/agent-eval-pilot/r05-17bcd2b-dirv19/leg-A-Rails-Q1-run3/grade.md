# Leg A-Rails-Q1-run3 — GRADE (operator model, harness-metered, v1.9, r05)

## Verdict: PASS — mechanism exact, 10 calls, roster declined at leash

Entry macro, builder, collection hooks, runtime classes all cited
with lines. Roster honestly declined (named the exact next reads).
Second run in three to burn a call on bare `--help` — pattern noted
for the directive (flag discovery), not a guard violation.

## Tokens (harness session truth, provider-native units)

Session `ses_f221702c7ffehs2cR0XBo2Kval` (muse-spark):
in=19,002 / out=1,699 / reasoning=2,420 / cache_read=124,266.
Primary (in+out): **20,701**.

## Context differential (what the window actually holds)

Fresh in 19,002 / re-reads 124,266 / out 1,699 / peak ctx 18,265 /
cache share 87%. No mid-run cache miss (seq5 uncached = first call,
normal).

## Ladder audit (from session log, 8 shell + 2 read)

init → probe → smart-map `"has_many"` (skip) → `--help` (waste) →
detect `has_many` → symbols `HasMany` → read 1420–1479 → read
builder head → symbols `CollectionAssociation` → path-arg T1/MAP
call → answer at leash. Guards untriggered. v1.9 ladder followed.

## Running tally (Rails A, T4 build)

| Run | Calls | Truth in+out | Peak ctx | Note |
|---|---|---|---|---|
| run1 | 10 | 29,909 | 19,480 | cache miss seq43 |
| run2 | 10 | 18,439 | 17,450 | clean; best answer |
| run3 | 10 | 20,701 | 18,265 | clean; --help waste |
| mean (n=3) | 10.0 | 23,016 | 18,398 | spread 11.5k ≈ single-miss scale |
