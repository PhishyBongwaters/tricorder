# Leg A-G1 attempt 1 — GRADE

## Verdict: PASS

Ground truth (`mgc.go` / `gcBgMarkWorker`, `markroot` area) cited with
line + signature and verified by reads — plus the full mark-phase map
(`gcMark:1972`, `gcMarkDone:997`, `gcMarkTermination:1360`, mgcmark.go
helpers). 5/20 calls.

## Tokens (agent-visible result payloads, `meter_leg.py`, tiktoken cl100k)

| Cmd | Step | Tokens | Note |
|---|---|---|---|
| 1 | MAP 2048 | 0 | timed out at agent's 120s, nothing delivered |
| 2 | symbols `gcBgMarkWorker` | 374 | exact-first hit, direct answer |
| 3 | read mgc.go 1766–1931 | 2,182 | full worker body (167 lines) |
| 4 | symbols `gcMark` | 1,275 | mark-phase map |
| 5 | read mgc.go 1972–1999 | 442 | entry header |
| **Total** | | **4,273** | |

## Compliance

- Full ladder as written (MAP rung 1 attempted, no skip). Ladder order
  held after the timeout: SYMBOLS → READ → SYMBOLS → READ.
- v1.3 exact-first: obeyed twice (cmds 2, 4 both identifier guesses, no
  NL query spent at all this leg).
- No junk encountered; v1.2 untriggered. Citation discipline clean.

## Findings

1. **MAP still times out with ranks live.** Cmd 1 ran against the
   canonical DB (file_ranks fresh, 10,767 files) and still delivered
   nothing in 120s. file_ranks killed the power-iteration cost, so the
   remainder — stream 1.4M def rows + sort + budget-fit loop + render —
   alone exceeds leg patience. MAP-skip on Go is confirmed as protocol
   (mapping-time by the scope lock), and the fit/render remainder is now
   the quantified next perf item.
2. **Cheapest passing A-leg yet:** 5 calls. Both identifier guesses hit
   directly; the leg never needed DETECT, NL, or tier escalation.
