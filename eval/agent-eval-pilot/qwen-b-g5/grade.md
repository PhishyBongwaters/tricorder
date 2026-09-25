# Qwen B-Go-G5 — GRADE (harness-metered)

## Verdict: PASS — correct with full driver chain, no repeats

Ground truth (`ssa.go:302 func buildssa`) cited exact with body
evidence (NewFunc :365, stmtList walk :583, insertPhis :602); full
chain verified (main.go:45 → gc.Main → compileFunctions :136 →
ssagen.Compile pgen.go:305 → buildssa :306 → ssacompile.Compile
pass pipeline). Zero exact-repeat tool calls in 51 harness tools.

## Tokens (harness session truth, provider-native units)

Session `ses_f26996db8ffewbQ0tgX3rbGKEW` (Qwen/llamacpp):
in=42,637 / out=5,435 / reasoning=0 / cache_read=1,182,679.
Primary (in+out): **48,072**.

## Behavior (from session log)

51 harness tools vs 20 cap (datum, not a verdict). Varied throughout:
scoped greps narrowing compile→ssagen→ssa→ssaconfig, reads 50–120
lines, no dead query re-issued. The loop pathology did NOT reproduce
on the baseline arm — grep hits are binary (hit/miss), leaving nothing
ambiguous to re-query.

## Model-matched context (signal only — mixed builds, see note)

| Pair | A truth | B truth | A/B |
|---|---|---|---|
| Operator model, r03 (same build) | 12,515 | 20,781 | **0.60×** |
| Qwen, A-voided (324377c) vs B (46d32c1) | 46,869 | 48,072 | **~0.98×** |

Note: the Qwen pair spans two builds (rescue fix landed between) and
a voided round — same-question signal, not a valid round pair. Qwen
tax vs operator model on identical arms: ~2–4× (B: 48k vs 20.8k;
A: 46.9k vs 12.5k).
