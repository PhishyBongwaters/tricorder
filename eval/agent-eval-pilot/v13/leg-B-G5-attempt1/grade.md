# Leg B-G5 attempt 1 — GRADE

## Verdict: PASS

Ground truth (`ssa.go:302 func buildssa`) cited with line + signature and
verified by reads, plus the full chain the A-leg never reached
(`pgen.go:305 Compile` wrapper → `gc/compile.go:174` driver loop).
16/20 calls.

## Tokens (reproduced payloads, `meter.py`, tiktoken cl100k)

| Cmds | Step | Tokens |
|---|---|---|
| 1–5 | listings root→internal | 494 |
| 6 | ssagen+ssa listings | 272 |
| 7–10 | greps (funcs, sizes, pgen, recursive) | 812 |
| 11–14, 16 | reads (pgen, ssa head/setup/tail, driver) | 2,863 |
| 15 | lowering grep | 299 |
| **Total** | | **4,740** |

## Compliance

- Baseline-only: clean — reads, listings, grep throughout; zero
  tricorder invocations. Same model both sides (pilot method).
- Citation discipline: every fact read first; checked file sizes before
  ranging the 274KB ssa.go (never read whole). One harness error (bad
  `-Include`, cmd 9 second half) cost a turn, recovered.
- Navigation cost is real: 5 listings (766 tokens) just to walk
  root→ssagen — the "even listing is expensive at Go scale" finding from
  the pilot, reproduced.

## A/B (G5 pair, v1.3 series)

| Leg | Verdict | Calls | Tokens |
|---|---|---|---|
| A-G5 attempt 2 | PASS | 7 | 3,068 |
| B-G5 attempt 1 | PASS | 16 | 4,740 |

First true v1.3 A/B pair: both PASS. Tricorder leg cheaper (0.65× tokens,
0.44× calls); baseline leg found further (driver loop). Neither leg is
being asked to generalize beyond G5 — one pair is a datum, not a verdict.
