# Leg A-VW-Q3 attempt 2 — GRADE (Qwen model)

## Verdict: PASS — **compliant, exact citations**

Correct answer: three-layer permission model with 8 ground-truth
citations across 6 files (collection.rs, group.rs, organization.rs,
cipher.rs, auth.rs, organizations.rs). 15/15 CLI calls + 12 reads,
8,708 tokens.

## Tokens

| Step | Tokens | Note |
|---|---|---|
| probe | 64 | held |
| MAP | 0 | skipped per v1.6 (5th leg running) |
| detects 7 × (5) | 3,255 | all capped, all hits |
| symbols 7 × (5) + T1 | 2,631 | capped, targeted |
| reads 12 × | 3,672 | bodies + enforcement |
| **Total** | **8,708** | |

## Compliance

- v1.6 obeyed: probe → exact detect names file → MAP skipped.
- Amended v1.3 obeyed: ALL 14 first passes capped at 5 (detects 7, symbols 7).
- v1.4/v1.5: reads ≤120 lines, one window per file, no chained pairs.
- T1 step 10 (no body) unread — correct v1.2 discipline.
- Minor: detect 2 (`collection_access`) noise (1 hit), not widened — correct.

## VW-Q3 across attempts

| | Att.1 (Nemotron, v1–v1.3) | Att.2 (Qwen, frozen) |
|---|---|---|
| Calls | 6 | 15 (cap) |
| Tokens | 4,638 | 8,708 (1.88×) |
| MAP | paid (map-first era) | skipped (v1.6) |
| Citations | exact | exact |
| Compliance | PASS | PASS |

Att.1 was map-first era (6 calls, 4.6k tok — best VW number). Att.2
pays more due to v1.6 probe+detect overhead before MAP skip, but
citations are equally exact. Pair ratio vs B will be comparable.

## Model Tracking

| Leg | Model | Provider |
|---|---|---|
| A-VW-Q3 att.2 | **Qwen** | **llamacpp** |
| A-VW-Q1/2 att.2, B-VW-Q1/2 att.2 | Qwen | llamacpp |
| A-VW-Q3/4 att.1 | Nemotron | opencode |
| Rest of Qwen-everywhere program | Qwen | llamacpp |

## Findings

1. **Query-conditioned MAP works**: `--mention` flag (1A) would have
   skipped the 2-step probe+detect sequence here, saving ~1k tok.
2. **VW permission code is diffuse**: 8 functions across 6 files — the
   question forces breadth. Single-file questions (Q1, Q2) win on
   tokens; diffuse questions cost more even with exact-first discipline.
3. **v1.6 probe+detect overhead is real**: 64 + 3,255 = 3,319 tok spent
   before MAP-skip pays off. On a single-file question the arithmetic
   breaks even; on multi-file it's a net cost.