# Leg B-Rails-Q1-run3 — GRADE (operator model, harness-metered, baseline)

## Verdict: PASS — complete, 11 calls (agent self-reported 9)

Full pipeline + generated API with line cites. Third self-report
mismatch in four legs (11 harness vs 9 claimed) — the pattern is
confirmed: agents undercount 1–2 calls routinely. Harness rows meter.

## Context (scored — what the window actually holds)

Peak ctx/call: **22,118**. Fresh in 41,541 / re-reads 44,597 /
out 1,711 / cache share 52%.

## Billing (context, never verdict)

Primary (in+out): 43,252 — nearly double run1/run2 on IDENTICAL
context (22.1k vs 22.8/23.0k). This run ate a massive cache miss
(cache_read 44.6k vs ~130k); the billing metric calls it an outlier,
the context metric calls it a normal run. Both recorded; context scores.

## Running tally (Rails B, context-scored)

| Run | Calls | Peak ctx | Primary | Note |
|---|---|---|---|---|
| run1 (r04) | 15 | 22,783 | 25,466 | |
| run2 | 13 | 22,964 | 25,595 | |
| run3 | 11 | 22,118 | 43,252 | cache-miss run; context flat |
| mean (n=3) | 13.0 | 22,622 | 31,438 | billing spread 17.8k, ctx spread 0.8k |
