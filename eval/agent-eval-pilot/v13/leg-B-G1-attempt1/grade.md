# Leg B-G1 attempt 1 — GRADE

## Verdict: PASS

Ground truth (`mgc.go` / `gcBgMarkWorker`, `markroot`) cited with lines
and verified by reads — plus drain internals (`gcDrain:1253`, wrappers),
the spawn site (`mgc.go:1711`), and the orchestration map. Deepest leg of
the series so far. 10/20 calls.

## Tokens (reproduced payloads, `meter.py`, tiktoken cl100k)

| Cmds | Step | Tokens |
|---|---|---|
| 1 | listing src/runtime | 4,640 |
| 3, 7, 8 | greps | 1,159 |
| 4 | sizes | 30 |
| 5, 6, 9, 10 | reads | 8,053 |
| **Total** | | **13,882** |

## Compliance

- Baseline-only: clean. One harness error (bare grep, cmd 2), recovered
  immediately with `Select-String`.
- Reads are large (up to 240 lines) but always pre-sized via step 4 —
  never blind. Citation discipline clean.

## A/B (G1 pair, v1.3 series)

| Leg | Verdict | Calls | Tokens |
|---|---|---|---|
| A-G1 attempt 1 | PASS | 5 | 4,273 |
| B-G1 attempt 1 | PASS | 10 | 13,882 |

Second v1.3 pair: both PASS, tricorder leg at 0.31× tokens and 0.5×
calls. The pilot's cost anatomy reproduces exactly: `ls src/runtime`
costs 4,640 here as in GO.md, and wide baseline reads dominate (58% of
the leg). The baseline's extra depth (drain bodies, spawn site) came from
reads the tricorder leg never needed for the question asked.
