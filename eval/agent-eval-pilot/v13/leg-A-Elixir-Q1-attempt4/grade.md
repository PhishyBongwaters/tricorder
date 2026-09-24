# Leg A-Elixir-Q1 attempt 4 — GRADE (Qwen model)

## Verdict: PASS — **NON-compliant (walk + detect spam), citation-inaccurate**

Substance and file+symbols right; every callback line ~60 late; 8 chained
windows cover 1–960; 5 detect wordings vs rung-2 max 2. 15/15 calls.

## Tokens

| Step | Tokens | Note |
|---|---|---|
| probe | 66 | held |
| MAP | 0 | skipped per v1.6 — the one thing that held |
| detects 5 × + symbols | 3,097 | capped but FIVE wordings |
| reads 8 × 120 | 9,250 | whole-walk 1–960 |
| **Total** | **12,413** | worst of the compliant era |

## Compliance

- v1.6 (probe → detect → skip MAP) obeyed exactly — then everything else
  regressed: rung-2 wording budget blown (5 vs 1–2 max), rung-4 ceiling
  used as a walk template (8 × 120 = whole file in compliant-looking
  chunks), zero locating greps.
- v1.6 moved spend, didn't cut it: saved 2,079 MAP, spent +2,100 extra
  detects/windows vs att.2. The ceiling became a stride length.
- Citation accuracy collapsed independently of shape — no rule addresses
  line-number fidelity; transcript audit is the only detector (same class
  as B-Vue-Q1's unread-file citations).

## Attempts 1 → 4

| | Att.1 | Att.2 (v1.4) | Att.3 (v1.5) | Att.4 (v1.6) |
|---|---|---|---|---|
| Calls | 9 | 14 | 12 | 15 (cap) |
| Tokens | 17,357 | 10,264 | 10,359 | 12,413 |
| Shape | 5 × 200–300 walk | bodies+greps | 8 × 20–150 walk | 8 × 120 walk |
| Citations | approximate | exact | exact (−1 block ×2) | ~60 late |
| Compliance | FAIL | PASS | v1.5-non-compliant | NON-compliant |

## Program-level finding

Freezing the directive didn't freeze behavior. Same model, same question,
same DB, four attempts: 10.3k→12.4k, PASS→NON-compliant, exact→~60-late.
**Attempt variance dominates rule tweaks.** The Qwen-everywhere program
must report pair outcomes as ranges/patterns across attempts, not point
numbers — single legs are noisy draws.

## Model Tracking

| Leg | Model | Provider |
|---|---|---|
| A-Elixir-Q1 att.1–4 | **Qwen** | **llamacpp** |
| A-Vue-Q1 att.1–3, B-Elixir-Q1, B-Vue-Q1 | Qwen | llamacpp |
| A-VW-Q3/Q4, A-G1-Qwen, A-Rails-Q1, B-Rails-Q1 | Qwen | llamacpp |
| All other v1.3 A-legs | Nemotron | opencode |
