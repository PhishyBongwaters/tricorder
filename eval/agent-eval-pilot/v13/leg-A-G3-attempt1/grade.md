# Leg A-G3 attempt 1 — GRADE

## Verdict: PASS

Ground truth (`chan.go` / `chansend` + `chanrecv`) cited with lines +
signatures and verified by reads, wrappers mapped (`chansend1:160`,
`chanrecv1:500`, `chanrecv2:505`). 6/20 calls. (Bodies verified at
header depth only — same caveat as pilot A-G3 — but signatures +
wrappers + call relations are all read-confirmed.)

## Tokens (agent-visible result payloads, `meter_leg.py`, tiktoken cl100k)

| Cmd | Step | Tokens | Note |
|---|---|---|---|
| 1 | MAP 2048 | 0 | timed out at agent's 120s (3rd consecutive leg) |
| 2 | `--help` | 1,665 | syntax discovery — 34% of the leg on overhead |
| 3 | symbols `chansend` | 1,323 | exact-first hit |
| 4 | symbols `chanrecv` | 1,310 | exact-first hit |
| 5–6 | reads (24 + 32 lines) | 618 | verified |
| **Total** | | **4,916** | |

## Compliance

- Full ladder as written. Exact-first twice, zero NL spent (third
  straight A-leg with no natural-language query).
- No junk encountered. Citation discipline clean.

## Findings

1. **MAP timeout now 3/3 legs** (A-G5 throwaway-DB, A-G1 + A-G3
   canonical-DB with ranks live). Rung 1 is unreachable on Go regardless
   of index state — settled as protocol, and the fit/render remainder is
   the quantified perf item.
2. **`--help` cost is real.** A fresh agent spent 1,665 tokens (a third
   of the leg) just learning CLI syntax. Machine-readable ladder
   knowledge (skill file, MCP tool schemas) is the reason MCP legs
   wouldn't pay this — a point for the MCP-surface comparison the pilot
   never ran.
