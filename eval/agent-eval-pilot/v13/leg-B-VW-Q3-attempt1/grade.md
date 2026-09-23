# Leg B-VW-Q3 attempt 1 — GRADE

## Verdict: PASS

Ground truth (`is_coll_manageable_by_user` at `collection.rs:570`,
`can_access_collection` at `collection.rs:155`) cited with lines and
verified by reads — plus API layer, cipher layer, and data model
flags. 8/20 calls. Deepest baseline leg of the VW series.

## Tokens (reproduced payloads, `meter.py`, tiktoken cl100k)

| Cmds | Step | Tokens |
|---|---|---|
| 1, 4, 8 | listings + sizes | 101 + 1,834 + 775 = 2,710 |
| 2, 3, 5 | greps | 2,291 + 1,999 + 2,187 = 6,477 |
| 6, 7 | reads | 562 + 964 = 1,526 |
| **Total** | | **10,713** |

## Compliance

- Baseline-only: clean. No harness errors.
- Citation discipline clean; reads pre-sized where possible.

## A/B (VW-Q3 pair, v1.3 series)

| Leg | Model | Verdict | Calls | Tokens | Ladder |
|---|---|---|---|---|---|
| A-VW-Q3 | Qwen (llamacpp) | PASS | 6 | **4,638** | Compliant |
| B-VW-Q3 | Nemotron | PASS | 8 | 10,713 | Clean |

Both PASS. Tricorder leg at **0.43× tokens and 0.75× calls** — the
widest margin in the VW series. Qwen's exact-first symbol hits on a
small repo with good name matches produced the most efficient A-leg of
the entire series. Baseline's broad greps (4,290 tokens just for the
first two searches) mirror the junk-payload class that tricorder now
defends against with three stacked gates.