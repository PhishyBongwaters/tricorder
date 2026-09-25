# Leg B-Go-G5 — GRADE (operator model, harness-metered)

## Verdict: PASS — clean baseline, 5 calls

Ground truth (`ssa.go:302 func buildssa`, caller `pgen.go:305/306
Compile`) cited exact with body evidence. No tricorder contact.

## Tokens (harness session truth, provider-native units)

Session `ses_f269ba64affeV2v4Zt8TS2TEXP` (muse-spark):
in=20,024 / out=757 / reasoning=406 / cache_read=35,524.
Primary (in+out): **20,781**.

## Ladder audit (from session log)

1. Prompt read (scaffolding).
2. Repo listing.
3. Grep `func.*build.*SSA|SSA.*build|buildssa` scoped to
   `src/cmd/compile` → direct hit.
4. Read `ssa.go:290-369` → body verified.
5. Read `pgen.go:280-339` → caller chain verified → answer.
No repeats, no dead queries. Strong baseline play.

## A/B (Go-G5, r03 — same model, same question, same build)

| | Calls (harness tools) | Truth in+out |
|---|---|---|
| A (tricorder) | 4 (3 substantive) | 12,515 |
| B (baseline) | 5 (4 substantive) | 20,781 |
| **A/B** | | **0.60×** |
