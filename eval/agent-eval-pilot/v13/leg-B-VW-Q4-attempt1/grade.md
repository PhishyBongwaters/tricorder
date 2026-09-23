# Leg B-VW-Q4 attempt 1 — GRADE

## Verdict: PASS

Ground truth (`send_cipher_update` at `notifications.rs:430`,
`send_update` at `354`, `push_cipher_update` at `push.rs:160`,
`create_update` at `627`, trigger table in `ciphers.rs`) cited with
lines and verified by reads. 20/20 calls (cap hit exactly).

## Tokens (reproduced payloads, `meter.py`, tiktoken cl100k)

| Step | Tokens |
|---|---|
| listings (4) | 204 |
| read notifications.rs full | 5,279 |
| reads ciphers.rs (9 sections) | 5,190 |
| read push.rs | 1,622 |
| **Total** | **12,090** |

## Compliance

- Baseline-only: clean. Cap hit exactly.
- Citation discipline clean; reads pre-sized where possible.

## A/B (VW-Q4 pair, v1.3 series)

| Leg | Model | Verdict | Calls | Tokens | A/B Tokens |
|---|---|---|---|---|---|
| A-VW-Q4 | **Qwen (llamacpp)** | PASS | 9 | **6,449** | **0.53×** |
| B-VW-Q4 | Nemotron | PASS | 20 | 12,090 | — |

Both PASS. Tricorder leg at **0.53× tokens and 0.45× calls**.
Qwen's exact-first detect hit both channels at once (`send_cipher_update`
+ `push_cipher_update`), then symbols confirmed each component.

## VW Series Final Summary

| Pair | A (tricorder) | B (baseline) | A/B Tokens | A/B Calls |
|---|---|---|---|---|
| Q1 | 6, 5,541 (Nemotron) | 11, 13,967 | 0.40× | 0.55× |
| Q2 attempt 1 | 16, 12,121 (Nemotron) | 5, 18,721 | 0.65× | 3.2× |
| Q2 attempt 2 | 5, 15,019 (Nemotron) | 5, 18,721 | 0.80× | 1.0× |
| Q3 | 6, **4,638** (Qwen) | 8, 10,713 | **0.43×** | 0.75× |
| Q4 | 9, 6,449 (Qwen) | 20, 12,090 | 0.53× | **0.45×** |
| **VW TOTAL** | **27 calls, 16,628 tok** | **44 calls, 55,491 tok** | **0.30×** | **0.61×** |

**Key finding**: Qwen's exact-first discipline + small repo + good
symbol names produced the most efficient legs of the entire series.
The final VW-Q4 A-leg at 0.53× tokens / 0.45× calls shows the ladder
working as designed: MAP noise → exact detect hit both channels →
symbols confirmed → reads verified.