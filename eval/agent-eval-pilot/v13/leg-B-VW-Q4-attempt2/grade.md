# Leg B-VW-Q4 attempt 2 — GRADE (Qwen model)

## Verdict: PASS — at cap (15/15), correct with exact citations

Baseline found all notification paths and cited exact lines. 15/15 calls
with all 4 whole-file reads. Self-count correct.

## Tokens

| Step | Tokens | Note |
|---|---|---|
| listings + greps | 1,377 | finding under 1.5k |
| reads 4 whole files | 11,584 | 89% of leg |
| **Total** | **12,961** | |

## VW-Q4 pair, Qwen/Qwen (frozen directive + smart-map tool)

| | Calls | Tokens |
|---|---|---|
| **A attempt 2 (--smart-map)** | **11** | **3,305** |
| B attempt 2 (baseline) | 15 | 12,961 |
| **A/B** | **0.73×** | **0.25×** |

**Smart-map Qwen vs baseline Qwen: 0.25× tokens.** Significant
improvement over att.1 map-first (6,449 → 0.51× A). Smart-map + Qwen
= 4× better than baseline.

## Model Tracking

| Leg | Model | Provider |
|---|---|---|
| A-VW-Q4 att.2, B-VW-Q4 att.2 | **Qwen** | **llamacpp** |
| A-VW-Q4 att.1, B-VW-Q4 att.1 | Nemotron/default | opencode |
| Rest of Qwen-everywhere program | Qwen | llamacpp |

## Findings

1. **Smart-map dominates baseline**: 3,305 vs 12,961 (0.25×) — 4× better.
2. **Baseline reads 92% whole files** (same pattern as all VW baselines).
3. **VW-Q4 is the 3rd VW pair where smart-map wins decisively**.

## Model Tracking

| Leg | Model | Provider |
|---|---|---|
| A-VW-Q4 att.2, B-VW-Q4 att.2 | **Qwen** | **llamacpp** |
| A-VW-Q4 att.1, B-VW-Q4 att.1 | Nemotron/default | opencode |
| Rest of Qwen-everywhere program | Qwen | llamacpp |