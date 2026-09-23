# Leg B-G3 attempt 1 — GRADE

## Verdict: PASS

Ground truth (`chan.go` / `chansend` + `chanrecv`) cited with lines +
signatures and verified by reads — plus struct, wrappers, and
select/reflect paths. 8/20 calls.

## Tokens (reproduced payloads, `meter.py`, tiktoken cl100k)

| Cmds | Step | Tokens |
|---|---|---|
| 1 | listing src/runtime | 4,640 |
| 3, 6 | greps + count | 271 |
| 4, 5, 7, 8 | reads | 1,805 |
| **Total** | | **6,716** |

## Compliance

- Baseline-only: clean. One harness error (bare grep/wc, cmd 2),
  recovered immediately with PowerShell equivalents.
- Citation discipline clean; reads pre-sized (line count first).

## A/B (G3 pair, v1.3 series)

| Leg | Verdict | Calls | Tokens |
|---|---|---|---|
| A-G3 attempt 1 | PASS | 6 | 4,916 |
| B-G3 attempt 1 | PASS | 8 | 6,716 |

Third v1.3 pair: both PASS, tricorder leg at 0.73× tokens and 0.75×
calls — the closest pair yet (G3's tight file locality favors grep).
The 4,640-token listing is 69% of the baseline leg: at Go scale,
navigation dominates both sides, and the A-leg's `--help` overhead
(1,665) is the same class of tax.
