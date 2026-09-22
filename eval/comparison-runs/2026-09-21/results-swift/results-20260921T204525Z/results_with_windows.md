# Swift-repo A/B: baseline vs branch head, with local-model window analysis

Windows referenced: 32k / 64k / 128k (typical 16GB-VRAM local models).
Delta = branch − baseline. Negative delta = branch saved tokens.

## Per-question results

| Question | Baseline tok | Branch tok | Δ raw | Δ % | Baseline calls | Branch calls | Baseline pass | Branch pass | Window flag |
|---|---|---|---|---|---|---|---|---|---|
| Q1-typecheck-call | 27,276 | 2,242 | -25,034 | -91.8% | 2 | 2 | PASS | PASS | — |
| Q2-sil-inliner | 2,509 | 1,411 | -1,098 | -43.8% | 2 | 2 | PASS | PASS | — |
| Q3-string-interp | 1,859 | 1,877 | +18 | +1.0% | 2 | 2 | PASS | PASS | — |
| Q4-parse-expr | 18,809 | 2,191 | -16,618 | -88.4% | 2 | 2 | PASS | FAIL | — |
| Q5-name-lookup | 19,422 | 2,068 | -17,354 | -89.4% | 2 | 2 | PASS | PASS | — |

## Totals

- Tokens: baseline 69,875, branch 9,789 → Δ -60,086 (-86.0%)
- Pass: baseline 5/5, branch 4/5

## Where the totals sit vs local-model windows

- 32k window: all-questions baseline total 69,875 → OVERFLOWS; branch total 9,789 → fits
- 64k window: all-questions baseline total 69,875 → OVERFLOWS; branch total 9,789 → fits
- 128k window: all-questions baseline total 69,875 → fits; branch total 9,789 → fits

## Per-question window placement (single-question navigation budget)

- Q1-typecheck-call: 32k: base fit/branch fit; 64k: base fit/branch fit; 128k: base fit/branch fit
- Q2-sil-inliner: 32k: base fit/branch fit; 64k: base fit/branch fit; 128k: base fit/branch fit
- Q3-string-interp: 32k: base fit/branch fit; 64k: base fit/branch fit; 128k: base fit/branch fit
- Q4-parse-expr: 32k: base fit/branch fit; 64k: base fit/branch fit; 128k: base fit/branch fit
- Q5-name-lookup: 32k: base fit/branch fit; 64k: base fit/branch fit; 128k: base fit/branch fit
