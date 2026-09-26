# Leg A-Rails-Q1 — GRADE (operator model, harness-metered)

## Verdict: PASS — compliant, 14 calls

Ground truth (`has_many`,
`activerecord/lib/active_record/associations.rb:1426` →
`Builder::HasMany.build()` → reflection registration; generated
`collection*`/`*_ids` method family) cited exact with file+line+symbol
throughout, including `builder/has_many.rb` (`valid_options`,
`valid_dependent_options`). Answer complete.

## Tokens (harness session truth, provider-native units)

Session `ses_f22d9d7daffeFUHq9jC2DV3FrJ` (muse-spark):
in=22,871 / out=2,418 / reasoning=1,024 / cache_read=205,486.
Primary (in+out): **25,289**.

## Ladder audit (from session log)

init → probe (3,576 files → under-5000 smart-map path) → smart-map
(junk JS hits, MAP correctly skipped) → detect `has_many` (exact hit)
→ symbols `HasMany` (test-only hits, correctly not read) → reads of
`associations.rb` doc/body windows → detect `Builder HasMany build`
(junk) → grep `class HasMany` in `builder/` → read `has_many.rb` →
answer. Eval guards untriggered (no repeats, steady progress).

## Comparison (Rails-Q1 A-arm, mixed builds — signal only)

| Leg | Calls | Truth in+out | Note |
|---|---|---|---|
| v13 att1 (Nemotron, map-first) | 7 | — (no harness row; artifact 8,014) | map-first, stopped early |
| r03 A-Q1 | 14 | 25,289 | smart-map skip + doc-heavy reads |
