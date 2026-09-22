# Agent eval 2.0 pilot — Go A/B (2026-09-22)

CLI-first agent eval: tricorder directive (A-legs) vs baseline grep/read
(B-legs). Same model (me) both sides; B instructed baseline-only, transcripts
audited for tricorder use (none found). Hard cap 20 calls/leg.
Corpus: `D:\Projects\Tricorder-Testing-Repos\go` (15,844 files).
Tricorder tip @ `202607d`. Directive v1 (ladder 0 init → 1 map → 2 detect →
3 symbols → 4 read → 5 tier-1 → 6 full file).

Leg score = sum of agent-visible result-payload tokens
(`utils.count_tokens`, tiktoken cl100k). Timed-out calls delivered nothing
(0 tokens, burned turns only). Directive text excluded. Wall-clock NOT
scored (context conservation only). Cold prescans uncharged; all A-legs ran
cold (map timed out on 16k files every leg — first cold receipt: even a
600s budget didn't finish under 3-way parallel contention).

## Verdicts (ground-truth citation grading)

| Leg | Cited | Ground truth | Verdict | Calls | Tokens |
|---|---|---|---|---|---|
| A-G1 | `mgc.go:1766` `gcBgMarkWorker` + drain loop | mgc.go / gcBgMarkWorker | PASS | 7 | 3,196 |
| B-G1 | `mgc.go:1766` + drain/entry | same | PASS | 7 | 9,533 |
| A-G3 | `chan.go:168` `chansend`, `:516` `chanrecv` | chan.go / chansend+chanrecv | PASS (bodies unverified — transcript lists no read commands) | 5 | 1,995 |
| B-G3 | `chan.go` + 8 funcs w/ lines | same | PASS | 7 | 6,220 |
| A-G5 | `ssa.go:302` `buildssa` | ssa.go:302 / buildssa | PASS | 6 | 59,717 (1,093 clean) |
| B-G5 | `ssa.go:302` + `Compile` chain | same | PASS | 9 | 89,487 |

Batch: A 64,908 vs B 105,240 (**1.6×**). A-clean (minus one junk query):
6,284 vs 105,240 (**17×**).

## Finding: failed NL queries dominate cost

A-G5's first query ("build SSA form for function") returned junk JS hits
costing **58,624 tokens** — the single most expensive step in the batch,
50× the leg's clean cost (1,093). The agent self-corrected (`BuildSSA` →
312 tokens) and passed, but the damage was done. Directive v1.2 must add:
*after any detect whose hits are wrong-language/wrong-area, retry an exact
symbol guess immediately; never read junk hits.* This is the same crowding
class as Swift Q4, at the query-formulation layer.

## Cost anatomy (both sides pay for scale)

- `ls src/runtime` = 4,640 tokens (both B-G1/B-G3 paid it — even listing
  is expensive at Go scale).
- B-G5's whole-`ssa.go` read = 87,360 tokens (98% of its leg).
- A-leg JSON payloads run 150–1,150 tokens per call when queries hit.

## Files

- `meter_go.json` — per-part token counts backing the table above
- `meter_go.py` — the metering script (re-runs A queries against the warm
  `eval-go-*.db` files, measures B reads/greps from disk)
