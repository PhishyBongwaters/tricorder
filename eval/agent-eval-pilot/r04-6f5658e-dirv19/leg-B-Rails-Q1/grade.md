# Leg B-Rails-Q1 — GRADE (operator model, harness-metered, baseline)

## Verdict: PASS — complete, 15 calls (at cap)

Full pipeline (entry macro → builder validation/accessors/callbacks →
reflection → runtime proxy ops) plus the generated-methods roster,
lifted from the documented `associations.rb:1152–1248` block the agent
found by grep and read directly. Every fact cited file+line+symbol.
Note: agent self-reported 13 calls; harness session rows show 15 tool
parts — self-reports are not metering (method restated).

## Tokens (harness session truth, provider-native units)

Session `ses_f2234e894ffed1p7J3W8YJOYmu` (muse-spark):
in=23,131 / out=2,335 / reasoning=225 / cache_read=128,761.
Primary (in+out): **25,466**.

## Trail audit (from session log)

grep `def has_many` → glob → grep (scoped) → read 1350–1509 (def
region) → read 1150–1349 (doc block = the money read, roster inside)
→ glob builder/ → read has_many.rb + collection_association.rb +
association.rb → glob → grep `class HasManyAssociation` → read
collection_association + has_many_association → grep proxy ops +
reflection. No repeats, no identical-twice, steady progress. Baseline
constraints honored (grep/glob/read only, no tricorder).

## Comparison (Rails-Q1 pair, harness truth throughout)

| Leg | Calls | Truth in+out | Note |
|---|---|---|---|
| r04 A-Q1 | 10 | 18,428 | leash-hit; mechanism exact, roster declined |
| r04 B-Q1 | 15 | 25,466 | at cap; mechanism + roster complete |

Pair: **0.72× — INVERSION** (greppable question loses for tricorder,
same shape as the v13 VW inversions). A is cheaper but less complete;
token savings is the only scored metric, completeness is context.
CONFOUNDED on the A side only (rebuilt DB + T2/T3); B touched no
tricorder code path.
