# Leg A-Rails-Q1-run2 — GRADE (operator model, harness-metered, v1.9, r05)

## Verdict: PASS — complete, 10 calls

Best answer of the three A-runs: mechanism exact AND roster derived
from code (`define_readers`/`define_writers` class_eval sites with
line cites), not the doc block. Clean ladder, no MAP, no repeats,
no blunders, no rescue needed on the recorded trail.

## Tokens (harness session truth, provider-native units)

Session `ses_f221a4ca5ffeLAv4NLCTmDyS3P` (muse-spark):
in=16,686 / out=1,753 / reasoning=1,817 / cache_read=115,675.
Primary (in+out): **18,439**.

## Context differential (what the window actually holds)

Fresh in 16,686 / re-reads 115,675 / out 1,753 / peak ctx 17,450 /
cache share 87%. No cache miss on this run — contrast run1 seq43.

## Ladder audit (from session log, 7 shell + 3 read)

init → probe → smart-map `"has_many"` (skip) → detect `HasMany` →
symbols `has_many` → read 1415–1454 (contains 1426) → builder head →
symbols `CollectionAssociation` → read collection_association.rb →
read association.rb (7k, pipeline + accessors) → answer at leash.
Guards untriggered. v1.9 ladder followed.

## Running tally (Rails A, T4 build)

| Run | Calls | Truth in+out | Peak ctx | Note |
|---|---|---|---|---|
| run1 | 10 | 29,909 | 19,480 | cache miss seq43 (+9.5k billing, 0 ctx) |
| run2 | 10 | 18,439 | 17,450 | clean cache; best answer |
| mean (n=2) | 10 | 24,174 | 18,465 | spread dominated by the miss |
