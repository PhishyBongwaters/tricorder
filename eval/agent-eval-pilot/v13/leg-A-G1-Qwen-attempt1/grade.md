# Leg A-G1-Qwen attempt 1 — GRADE (Qwen model)

## Verdict: PASS — **Ladder compliant, exact-first, zero NL**

Ground truth (`mgc.go:1766 gcBgMarkWorker`, `mgcmark.go:1253 gcDrain`,
`mgc.go:733 gcStart`) cited with lines and verified by reads. 8/20 calls.

## Tokens

| Step | Tokens | Note |
|---|---|---|
| MAP 2048 | 0 | timeout (expected on Go, 4/4 legs) |
| detect "gcBgMarkWorker" | 1,065 | exact-first identifier guess |
| symbols "gcBgMarkWorker" | 374 | confirmed |
| detect "gcDrain" | 1,111 | exact-first identifier guess |
| symbols "gcDrain" | 809 | confirmed |
| reads (3 ranges) | 5,002 | verified |
| **Total** | **8,361** | |

## Compliance

- MAP rung 1: timed out (expected on Go, 4/4 legs) → correctly continued
- Exact-first: both detect queries were identifier guesses, zero NL
- Ladder: MAP → DETECT → SYMBOLS → DETECT → SYMBOLS → READ ×3
- **Stopped at first rung that answered** (READ rung confirmed full picture)
- Zero junk; zero NL; citation discipline clean

## Model Tracking

| Leg | Model | Provider |
|---|---|---|
| A-G1-Qwen | **Qwen** | **llamacpp** |
| A-G1 (Nemotron) | Nemotron 3 Ultra Free | opencode |

## Comparison (G1 pair)

| Leg | Model | Calls | Tokens | Ladder |
|---|---|---|---|---|
| A-G1 (Nemotron) | Nemotron | 5 | 4,273 | PASS |
| A-G1-Qwen | **Qwen** | 8 | **8,361** | PASS, compliant |
| B-G1 (Nemotron) | Nemotron | 10 | 13,882 | Clean |

## Findings

1. **Qwen used more tokens on Go** (8,361 vs 4,273) — the larger reads on Go (1,766–1,930 lines for gcBgMarkWorker, 1,252–1,419 for gcDrain) are unavoidable on the Go codebase; Nemotron stopped at smaller ranges.
2. **MAP rung still timeout on Go** — 4/4 legs now, regardless of model or ranks live. Settled as protocol.
3. **Qwen followed ladder exactly** — zero NL, zero junk, stopped at first answer. More disciplined than Nemotron on Q2.
3. **Read ranges larger on Go** — worker function spans 166 lines, gcDrain spans 168 lines; small-repo efficiency doesn't transfer to Go.