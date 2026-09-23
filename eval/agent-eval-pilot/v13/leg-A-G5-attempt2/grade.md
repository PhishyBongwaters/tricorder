# Leg A-G5 attempt 2 — GRADE

## Verdict: PASS

Ground truth (`src/cmd/compile/internal/ssagen/ssa.go:302 func buildssa`)
cited with line + signature, verified by read; caller chain (`pgen.go:305
Compile` → `buildssa`) confirmed by second read. 7/20 calls.

## Tokens (agent-visible result payloads, `meter_leg.py`, tiktoken cl100k)

| Cmd | Step | Tokens | Note |
|---|---|---|---|
| 1 | MAP 2048 | 0 | timed out at agent's 120s, nothing delivered |
| 2 | symbols `buildSSA` | 150 | exact-first hit, direct answer |
| 3 | bad powershell wrap | 0 | harness error, recovered |
| 4 | read ssa.go 296–335 | 544 | verified entry point |
| 5 | symbols `compileSSA` | 1,503 | fuzzy junk, correctly NOT read |
| 6 | detect NL ×5 | 650 | caller confirmation |
| 7 | read pgen.go 301–315 | 221 | verified caller |
| **Total** | | **3,068** | + unmetered error text (cmd 3) |

Metering correction (2026-09-23): first-published figures (16,149 total)
were ~5× inflated — payload artifacts were captured via PowerShell `>`
redirect (UTF-16LE) and counted as UTF-8, so every NUL byte tokenized.
`meter_leg.py` now detects NUL bytes and decodes UTF-16; figures above are
re-metered. The pilot's 58,624 figure is unaffected (captured in-process,
`meter_go.py`). Corrected comparison: this leg's NL step (650) is ~90×
smaller than the pilot's uncapped NL blowup.

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

1. **NL junk class: fixed at the source (post-leg).** Same query class that
   cost 58,624 tokens in the pilot now costs 650 under the ×5 cap — and the
   cmd-5 fuzzy junk (1,503 tokens of `*_ssa` test helpers for near-miss
   "compileSSA") is now a clean empty result (7 tokens,
   `step_symbols_compileSSA_postfix.txt`). Root cause: the rescue
   token-overlap gate accepted half-token matches (`overlap*2 >=
   len(qtok)` — sharing 1 of 2 tokens qualified). Fix: strict majority
   (`>`), both rescue passes (`core.py` search_identifiers +
   search_symbols), red-first test `tests/test_rescue_overlap.py` (3
   tests), full suite 477 passed. v1.2 discipline is still the backstop
   for other near-miss shapes, but this family no longer fires.
2. **MAP rung unreachable on Go even warm.** Cmd 1 timed out on a warm DB
   (map-text render is the known slow path — cf. run_go_eval's
   `--map-tokens 0` workaround). Ladder rung 1 is dead on 16k-file repos.
   Proposal for operator: record MAP-skip as explicit deviation for all
   future Go legs (start at rung 2).
3. **Metering gap:** the NL detect (cmd 6) took >100s wall in re-run
   (first metering attempt timed out at 120s with 3 artifacts done).
   Wall-clock is not scored this series, but NL substring queries are
   slow as well as junk-prone — second reason for exact-first.
