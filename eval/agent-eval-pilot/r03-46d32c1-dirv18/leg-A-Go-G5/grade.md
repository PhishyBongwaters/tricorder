# Leg A-Go-G5 — GRADE (operator model, harness-metered)

## Verdict: PASS — fully compliant, 3 calls

Ground truth (`src/cmd/compile/internal/ssagen/ssa.go:302 func
buildssa`) cited exact with signature; chain confirmed (`pgen.go:305
Compile` calls `buildssa` :306). Answer complete.

## Tokens (harness session truth, provider-native units)

Session `ses_f269d99b9ffeqTou5sce4vDrOS` (muse-spark):
in=11,769 / out=746 / reasoning=472 / cache_read=35,140.
Primary (in+out): **12,515**.

## Ladder audit (from session log, not self-report)

1. Prompt read (scaffolding).
2. `--detect "buildSSA" --max-results 5` (+root/+db-path) → exact hit.
3. `--symbols "buildssa" --max-results 5` → signature confirmed.
4. Read `ssa.go:302` +120 → body verified → answer.
- v1.8 obeyed: no rung-1 MAP on a 5000+ repo. Exact-first obeyed.
  No repeats, no junk queries, no fallback rungs needed.

## Comparison (same question, harness truth throughout)

| Leg | Calls | Truth in+out | Note |
|---|---|---|---|
| v13 A-G5-att2 | 7 | 15,251 | MAP timed out, forced detect-first |
| r02 A-G5 (voided) | 25 | 46,869 | Qwen wander, over cap |
| r03 A-G5 | 3 | 12,515 | v1.8 detect-first, tightest yet |
