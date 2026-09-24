# Leg B-Elixir-Q1 attempt 1 — GRADE (Qwen model)

## Verdict: PASS — at cap (15/15), correct with exact citations

Baseline found the file in 3 listings and read it cover-to-cover (9 chunks)
plus `behaviour.ex` whole. No ladder applies; graded on correctness + cap.

## Tokens

| Step | Tokens | Note |
|---|---|---|
| listings 3 × | 316 | file found in 3 steps |
| measures 2 × | 3 | one miscount (1073 vs 1376), harmless |
| reads 10 × | 13,729 | whole gen_server.ex + whole behaviour.ex |
| **Total** | **14,048** | reads = 98% |

## Elixir-Q1 pair (Qwen/Qwen, purest A/B)

| | Calls | Tokens |
|---|---|---|
| A attempt 1 (v1–v1.3, non-compliant) | 9 | 17,357 (1.24× B) |
| **A attempt 2 (v1–v1.4, compliant)** | **14** | **10,264 (0.73× B)** |
| B attempt 1 (baseline) | 15 | 14,048 |

Pre-fix tricorder LOST to baseline on tokens (1.24×) — the rung-4
over-read cost more than having no index at all. Post-fix A wins at
0.73× tokens, 0.93× calls. The v1.4 ceiling is the difference between
losing and winning this pair.

## Model Tracking

| Leg | Model | Provider |
|---|---|---|
| A-Elixir-Q1 att.1/att.2, B-Elixir-Q1 | **Qwen** | **llamacpp** |
| A-VW-Q3/Q4, A-G1-Qwen, A-Rails-Q1, B-Rails-Q1 | Qwen | llamacpp |
| All other v1.3 A-legs | Nemotron | opencode |

## Findings

1. **Baseline structural cost confirmed:** 98% of B tokens are file reads;
   3 listings (316 tok) did all the finding. Mirrors B-Rails-Q1 (14 reads).
2. **A-leg edge is read discipline, not finding:** both sides found the
   file in ≤3 steps; the gap is targeted bodies (7,067 tok) vs whole file
   (13,729 tok in reads).
