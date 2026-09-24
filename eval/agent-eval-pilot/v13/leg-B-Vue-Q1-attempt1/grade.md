# Leg B-Vue-Q1 attempt 1 — GRADE (Qwen model)

## Verdict: PASS — at cap (15/15), with citation-integrity flag

Baseline core answer correct from files actually read. Flag: exact-line
citations from `state.ts`, `array.ts`, `apiWatch.ts` have no provenance in
the 15-command record (closing note confabulates extra reads past the cap).

## Tokens

| Step | Tokens | Note |
|---|---|---|
| listings 9 × | 271 | finding cost near-zero |
| reads 6 whole files | 8,771 | 108–339 lines each |
| **Total** | **9,042** | reads = 97% |

## Vue-Q1 pair (Qwen/Qwen, purest A/B)

| | Calls | Tokens |
|---|---|---|
| **A attempt 1 (v1–v1.4)** | **13** | **10,177 (1.13× B)** |
| B attempt 1 (baseline) | 15 | 9,042 |

**Baseline WON on tokens.** Anatomy: A saved 2,603 tok in reads (6,168
targeted vs 8,771 whole-file) but spent 4,009 finding (MAP 2,061 noise +
4 detects 1,948). Net −1,135. When every answer file is ≤339 lines,
whole-file reads are cheap and index overhead dominates — the inverse of
Elixir, where the 1,376-line file made read discipline decisive (A 0.73×).

## Model Tracking

| Leg | Model | Provider |
|---|---|---|
| A-Vue-Q1, B-Vue-Q1 | **Qwen** | **llamacpp** |
| A-Elixir-Q1 att.1/att.2, B-Elixir-Q1 | Qwen | llamacpp |
| A-VW-Q3/Q4, A-G1-Qwen, A-Rails-Q1, B-Rails-Q1 | Qwen | llamacpp |
| All other v1.3 A-legs | Nemotron | opencode |

## Findings

1. **Small-file inversion.** MAP + 4 detects cost more than they save when
   answers fit in small whole files. Ladder's fixed rung-1 MAP is the
   dearest step on both Vue legs (2,061 tok, types-only noise).
2. **Finding is nearly free for baselines too** (271 tok listings) — the
   A-leg edge lives or dies on read-vs-find arithmetic per repo shape.
3. **Baseline citation hygiene fails silently:** unread-file citations with
   exact lines look identical to verified ones. A-legs have the same risk;
   the transcript audit is the only detector.
