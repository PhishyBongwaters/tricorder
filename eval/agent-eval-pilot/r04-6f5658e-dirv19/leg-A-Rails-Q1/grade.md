# Leg A-Rails-Q1 — GRADE (operator model, harness-metered, v1.9)

## Verdict: PASS — compliant, 10 calls (leash-hit), answer partial-by-design

Entry macro (`has_many`, `associations.rb:1426`, body read 1426–1429),
builder (`HasMany < CollectionAssociation`, `builder/has_many.rb:4`,
head-read), runtime classes (`HasManyAssociation:11`,
`HasManyThroughAssociation:6`) all cited exact with body evidence.
Generated-methods roster NOT enumerated — no tool window returned it
and the agent correctly declined to guess (leash fired at call 10).
Ground truth for the mechanism half: exact.

## Tokens (harness session truth, provider-native units)

Session `ses_f2248a5b5ffeIk8NphN2jcrSqC` (muse-spark):
in=16,652 / out=1,776 / reasoning=2,316 / cache_read=118,619.
Primary (in+out): **18,428**.

## Ladder audit (from session log, 8 shell + 2 read)

init → probe-digest (3509 files) → smart-map `"has_many"` (IDENTIFIER
rung 1 per v1.9; exact hit, MAP skipped — T2 live) → detect
`has_many` → symbols `has_many` (associations.rb:1426 head — T3 live)
→ read 1420–1479 (window CONTAINS cited line 1426; doc-walk ban
respected) → symbols `Builder::HasMany` (test-class head — stored
Ruby symbol names appear unqualified, so segment rank had nothing to
grip; agent routed around via rung 2) → detect `HasMany`
(builder/has_many.rb:4) → read builder head → symbols `--tier 1`
(rung 5) → leash → answer. Guards untriggered (no repeats, no
identical-twice, steady progress). v1.9 ladder followed rung by rung.

## Comparison (Rails-Q1 A-arm, harness truth throughout)

| Leg | Calls | Truth in+out | Note |
|---|---|---|---|
| r03 A-Q1 | 14 | 25,289 | pre-T1 DB, NL-question rung 1, doc-walk 5 calls |
| r04 A-Q1 | 10 | 18,428 | rebuilt DB + T2 skip + v1.9 ladder; leash-hit |

CONFOUNDED (per round README): directive + product (T2/T3) + rebuilt
DB. 0.73× is not quotable as a directive effect.
