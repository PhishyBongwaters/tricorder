# Leg B-VW-Q2 attempt 1 — GRADE

## Verdict: PASS

Ground truth (`AdminToken` guard `admin.rs:857`, `validate_token`
`admin.rs:229`, JWT chain `auth.rs`) cited with lines and verified by
full-file reads — plus login flow, cookie creation, claims, issuer.
5/20 calls. Deepest baseline leg of the series so far (two full-file
reads pre-sized at 8KB/927 lines and 10KB/1341 lines).

## Tokens (reproduced payloads, `meter.py`, tiktoken cl100k)

| Cmds | Step | Tokens |
|---|---|---|
| 1–3 | listings root→api | 172 |
| 4 | read admin.rs full | 8,321 |
| 5 | read auth.rs full | 10,228 |
| **Total** | | **18,721** |

## Compliance

- Baseline-only: clean. No harness errors.
- Full-file reads pre-sized (line counts first) — justified, not blind.
- Citation discipline clean; all facts read-first.

## A/B (VW-Q2 pair, v1.3 series)

| Leg | Verdict | Calls | Tokens |
|---|---|---|---|
| A-VW-Q2 attempt 1 | PASS | 16 | 12,121 |
| B-VW-Q2 attempt 1 | PASS | 5 | 18,721 |

Both PASS. Tricorder leg at 0.65× tokens and 3.2× calls — the
baseline's two full-file reads (18.5k tokens) exceed the tricorder leg's
entire budget. Note the baseline read `auth.rs` full (10.2k tokens) to
find what the tricorder leg found in 1,029 tokens via `detect
"encode_jwt"`. The A-leg's MAP rung (2,040) + tier 1 (2,054) cost is
real but targeted; baseline's full-file reads are the same junk-payload
class as the Go listing tax, just concentrated in two files.