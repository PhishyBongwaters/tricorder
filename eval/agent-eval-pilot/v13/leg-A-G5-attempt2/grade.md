# Leg A-G5 attempt 2 — GRADE

## Verdict: PASS

Ground truth (`src/cmd/compile/internal/ssagen/ssa.go:302 func buildssa`)
cited with line + signature, verified by read; caller chain (`pgen.go:305
Compile` → `buildssa`) confirmed by second read. 7/20 calls.

## Tokens (agent-visible result payloads, `meter_leg.py`, tiktoken cl100k)

| Cmd | Step | Tokens | Note |
|---|---|---|---|
| 1 | MAP 2048 | 0 | timed out at agent's 120s, nothing delivered |
| 2 | symbols `buildSSA` | 1,035 | exact-first hit, direct answer |
| 3 | bad powershell wrap | 0 | harness error, recovered |
| 4 | read ssa.go 296–335 | 542 | verified entry point |
| 5 | symbols `compileSSA` | 10,193 | fuzzy junk, correctly NOT read |
| 6 | detect NL ×5 | 4,159 | caller confirmation |
| 7 | read pgen.go 301–315 | 220 | verified caller |
| **Total** | | **16,149** | + unmetered error text (cmd 3) |

## Compliance

- Ladder: MAP → SYMBOLS → READ → SYMBOLS → DETECT → READ. DETECT skipped
  on first pass per v1.3 exact-first; acceptable.
- v1.3 exact-first: obeyed — first substantive query was the identifier
  guess, 1,035 tokens, direct hit.
- v1.3 NL cap (×5): obeyed (cmd 6).
- v1.2 junk-hit retry: obeyed in spirit — cmd 5's 10 fuzzy hits were
  judged wrong-area and never read; no retry was needed (answer in hand).
- Citation discipline: every fact from a hit. Clean.

## Findings

1. **NL junk class contained, not dead.** Same query class that cost
   58,624 tokens in the pilot now costs 4,159 (14× smaller: ×5 cap +
   interleave fix). But cmd 5 shows the fuzzy-rescue junk source still
   fires (10,193 tokens for a near-miss) — what saved this leg was agent
   discipline (v1.2), not the absence of junk. Possible product follow-up:
   cap or flag fuzzy-rescue payloads.
2. **MAP rung unreachable on Go even warm.** Cmd 1 timed out on a warm DB
   (map-text render is the known slow path — cf. run_go_eval's
   `--map-tokens 0` workaround). Ladder rung 1 is dead on 16k-file repos.
   Proposal for operator: record MAP-skip as explicit deviation for all
   future Go legs (start at rung 2).
3. **Metering gap:** the NL detect (cmd 6) took >100s wall in re-run
   (first metering attempt timed out at 120s with 3 artifacts done).
   Wall-clock is not scored this series, but NL substring queries are
   slow as well as junk-prone — second reason for exact-first.
