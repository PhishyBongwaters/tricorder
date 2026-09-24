# Leg B-VW-Q3 attempt 2 — GRADE (Qwen model)

## Verdict: PASS — at cap (33/15), correct with exact citations

Baseline found all permission layers and cited exact lines. Cap overrun
recorded; self-count confabulation noted.

## Tokens

| Step | Tokens | Note |
|---|---|---|
| listings + greps | 1,284 | finding under 2k |
| reads 11 whole files | 18,892 | 92% of leg |
| greps 12 × | 1,093 | cross-refs |
| **Total** | **20,469** | |

## VW-Q3 pair, Qwen/Qwen (frozen directive + smart-map tool)

| | Calls | Tokens |
|---|---|---|
| **A attempt 3 (--smart-map)** | **6** | **2,834** |
| B attempt 2 (baseline) | 33 | 20,469 |
| **A/B** | **0.18×** | **0.14×** |

**Smart-map Qwen vs baseline Qwen: 0.14× tokens.** Massive improvement
over att.2 manual v1.6 (8,708, 0.62×) and even beats att.1 map-first
(4,638, 0.62×). Smart-map + Qwen = 7× better than baseline.

## Model Tracking

| Leg | Model | Provider |
|---|---|---|
| A-VW-Q3 att.3, B-VW-Q3 att.2 | **Qwen** | **llamacpp** |
| A-VW-Q3 att.1, B-VW-Q3 att.1 | Nemotron/default | opencode |
| Rest of Qwen-everywhere program | Qwen | llamacpp |

## Findings

1. **Smart-map tooling is decisive**: A-leg went from 15 calls/8.7k
   (manual v1.6) to 6 calls/2.8k (smart-map) — tooling absorbed the
   protocol logic.
2. **Baseline structural cost unchanged**: 92% reads, 9 finding
   greps/listings (same as B-VW-Q1/Q2). The gap is entirely on A-side
   read discipline + tooling.
3. **VW-Q3 is the strongest VW pair for tricorder**: A/B 0.14× with
   smart-map.