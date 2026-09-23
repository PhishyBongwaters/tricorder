# Leg A-VW-Q1 attempt 1 — GRADE

## Verdict: PASS

Ground truth (`validate_totp_code`,
`src/api/core/two_factor/authenticator.rs:115`) cited with lines and
verified by reads, plus wrapper (`:101`) and caller (`:57/:83`). 6/15
calls. First full-ladder leg of the series (MAP rung answered, ladder
continued correctly past it).

## Tokens

Post-fix replay (product as it exists; series comparison figure):

| Cmd | Step | Tokens | Note |
|---|---|---|---|
| 1 | MAP 2048 | 2,040 | fitted; answered but no TOTP in top slice |
| 2 | symbols `verify_totp` | 164 | fuzzy near-miss, right area |
| 3 | detect NL ×5 | 593 | junk → fired v1.2 retry (textbook) |
| 4 | symbols `authenticator` | 1,215 | answer file located |
| 5–6 | reads (54 + 85 lines) | 1,529 | caller + answer body |
| **Total** | | **5,541** | |

As-run: cmd 1 delivered **218,527 tokens** (pre-fix JSON path ignored
the budget; artifact measured before the fix, not committed). The agent
reported "~100s hits ... truncated output" and continued correctly, but
metering scores what the CLI delivered. Series comparisons use the
post-fix replay; the as-run figure stands as the incident record.

## Compliance

- Full ladder as written, all 6 rungs respected in order.
- v1.3 exact-first (cmd 2), NL fallback capped ×5 (cmd 3), v1.2 retry on
  junk (cmd 3 → cmd 4) — every new rule exercised in one leg.
- Citation discipline clean.

## Findings

1. **JSON MAP ignored the budget — fixed.** `fit_json_tags`
   (`tricorder.py`; binary-search prefix fit on delivered JSON bytes,
   ≥1 tag fallback mirroring the text path), red-first
   `TestJsonMapBudget` (3 tests), verified 218,527 → 2,040 on the exact
   leg command. The cap regression suite (`test_map_budget.py`) never
   covered the JSON emit path — now it does.
2. **MAP answered but didn't resolve.** At 506 files the rung works
   mechanically (seconds, fitted) yet the top-2048 slice held no TOTP —
   generic high-rank names instead. Ladder behaved as designed (continue
   to detect). Whether top-slice recall at floor budgets needs work is a
   product question, not a leg failure.
