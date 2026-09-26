# Leg A-Rails-Q1 — GRADE (operator model, harness-metered, v1.9, r05)

## Verdict: PASS — complete, 10 calls

Mechanism (entry macro 1426–1428, builder valid options, runtime
classes) AND the generated-methods roster (1158–1217) cited exact
with body evidence. The roster came via a grep-directed read
(call 9 `methods.*will be added|collection\.` → call 10 window
1128–1232): tool-cited, not a creeping window — compliant with the
doc-walk ban by letter. One wasted call (call 6 `--help --format
json`, exit 1, ~95 lines dumped into context) noted as inefficiency,
not a guard violation.

## Tokens (harness session truth, provider-native units)

Session `ses_f22250609ffeM1mr4xrpMX0MFx` (muse-spark):
in=28,108 / out=1,801 / reasoning=1,447 / cache_read=110,314.
Primary (in+out): **29,909**.

## Ladder audit (from session log, 8 shell + 2 read)

init → probe-digest → smart-map `"has_many"` (identifier rung 1,
exact hit, MAP skipped — T2 live) → detect `has_many` → symbols
`HasMany` → `--help` blunder → read 1400–1459 (window CONTAINS cited
1426) → read builder head → grep roster pattern → read 1128–1232 →
answer at the leash. Guards untriggered. v1.9 ladder followed.

## Comparison (Rails-Q1 A-arm, harness truth throughout)

| Leg | Calls | Truth in+out | Note |
|---|---|---|---|
| r03 A-Q1 | 14 | 25,289 | pre-T1 DB, NL rung 1, doc-walk 5 calls |
| r04 A-Q1 | 10 | 18,428 | leash-hit; roster declined |
| r05 A-Q1 | 10 | 29,909 | leash-hit; roster recovered via grep-directed read |

r05-vs-r04 is product-only (same directive/DB/vehicle, build
6f5658e → 17bcd2b) BUT agent variance dominates: the +11k input is
better explained by the --help dump and fatter symbols payloads
(`HasMany` capitalized) than by T4 (no rescue fired on this trail —
call 5 hit the main path). Do not quote a T4 effect here.
