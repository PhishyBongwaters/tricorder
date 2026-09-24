# Leg B-Rails-Q1 attempt 2 — GRADE (Qwen model)

## Verdict: PASS — at cap (16/15), correct with exact citations

Baseline found all implementation layers and cited exact lines. Cap overrun by 1 call.

## Tokens

| Step | Tokens | Note |
|---|---|---|
| listings + greps | 1,544 | finding under 2k |
| reads 4 whole files | 11,305 | 81% of leg |
| greps 3 × | 146 | cross-refs |
| **Total** | **13,951** | |

## Rails-Q1 pair, Qwen/Qwen (frozen directive + smart-map tool)

| | Calls | Tokens |
|---|---|---|
| **A attempt 2 (--smart-map)** | **22** | **19,165** |
| B attempt 2 (baseline) | 16 | 13,951 |
| **A/B** | **1.38×** | **1.37×** |

**Baseline wins on tokens** (unusual for this series — A is more expensive because the answer is diffuse across 6+ files). Smart-map A still skipped MAP (2k saved) but spent 19.2k on 6 targeted reads vs B's 14k on 4 whole files. The Rails answer is inherently multi-file.

## Model Tracking

| Leg | Model | Provider |
|---|---|---|
| A/B Rails-Q1 att.2 | **Qwen** | **llamacpp** |
| A-VW-Q1–Q4, B-VW-Q1–Q4 | Qwen | llamacpp |
| A-Elixir-Q1, B-Elixir-Q1 | Qwen | llamacpp |
| A/Vue-Q1 | Qwen | llamacpp |
| All other v1.3 A-legs | Nemotron | opencode |

## Findings

1. **Rails answer is inherently diffuse**: 6 files needed for complete answer (associations.rb, has_many.rb, association.rb, collection_association.rb, has_many_association.rb, collection_proxy.rb, reflection.rb). Smart-map A still skipped MAP (2k saved) but spent 19.2k on 6 targeted reads vs B's 14k on 4 whole files.
2. **Baseline still reads whole files**: 81% of B tokens are whole-file reads — same pattern as all VW baselines.
3. **First VW/Rails pair where B wins on tokens**: A 1.37× B tokens. The diffuse nature of Rails answer means A's targeted reads cost more than B's brute force.