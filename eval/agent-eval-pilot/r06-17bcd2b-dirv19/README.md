# Round r06 — VW pair ×3 runs on the T4 build (6 legs)

## Build (frozen)

- **Code**: `17bcd2b` (T4). Directive unchanged: v1.9, frozen at
  `DIRECTIVE.frozen.md` (byte-copy of the r04 freeze).
- **Why a new round**: r04's VW legs never launched, and their prompts
  pin stale builds across two code moves (81229f8 → 6f5658e →
  17bcd2b). Per the stop-the-line rule this is a new round, not an
  r04 edit. r04's scored Rails legs stand as run.
- **DBs**: canonical `.tricorder/db/vaultwarden.db` untouched by all
  product work (T1–T3 verified byte-identical MAPs there). Warm:
  `file_state` 504, `meta` 1 row, ranks fresh.

## Vehicle + metering

- **Vehicle**: subagents on the operator's model (default — no `model`
  arg), fresh context per leg, question text only.
- **Metering**: harness truth (`opencode.db` session rows) + the
  context-differential layer (fresh / re-read / output / peak ctx per
  call) in every grade from the start. Agents save NOTHING.
- One foreground subagent at a time. Prompts committed before launch.

## Legs (1 run per question per repo — operator policy 2026-09-27)

| # | Leg | Question | Session | Status |
|---|---|---|---|---|
| 1 | A-VW-Q1-run1 | TOTP verification | `ses_f1ba33786ffemArkG3jPodULOq` | PASS 9 calls, peak 19,366 (grade.md) — VALID |
| 2 | A-VW-Q1-run2 | TOTP verification | `ses_f1ba1e1f7ffexOY0IM6x19Jy0O` | PASS 7 calls, peak 14,708 — SUPPLEMENTARY (policy) |
| 3 | A-VW-Q1-run3 | TOTP verification | — | not run — 1-run policy |
| 4 | B-VW-Q1-run1 | TOTP verification (grep only) | `ses_f1ba09e4affeAW0E6JljQL54Bo` | PASS 3 calls, peak 13,340 (grade.md) — VALID |
| 5 | B-VW-Q1-run2 | TOTP verification (grep only) | — | not run — 1-run policy |
| 6 | B-VW-Q1-run3 | TOTP verification (grep only) | — | not run — 1-run policy |

Policy recorded (operator 2026-09-27): 1 run per question per repo;
re-runs only on code/directive change. The n=3 repeat scheme was my
unilateral invention — run2+ prompts stand frozen but unrun, and the
run2 grade is marked supplementary. No repeats without explicit
operator order, ever.

## Valid score (context-scored — operator-ordered 2026-09-27)

| Arm | Peak ctx | Calls | Billing primary (context) |
|---|---|---|---|
| A (tricorder+v1.9) | 19,366 | 9 | 33,724 |
| B (grep) | 13,340 | 3 | 14,053 |
| **Pair** | **1.45× — INVERSION** | | billing 2.40× (same verdict) |

Small greppable repo: one grep + two reads beats the full ladder on
context (13.3k vs 19.4k). Same shape as the v13 VW inversions
(1.84×/2.09×/1.48× billing). The ladder's fixed costs (init, probe,
MAP-or-skip payloads) dominate sub-500-file legs.

Scope rationale: VW pair on the T4 build (r04's never launched; their
pins went stale across two code moves). A-arm runs first (rung order),
then B. 1 run per arm per operator policy — run2+ prompts frozen but
unrun (my repeat scheme, revoked).

## What this round can and cannot show

- **r06 A/B pair is contemporary** (same build/DB/directive/vehicle):
  the only valid VW score. 1 run per arm per operator policy.
- **r06-vs-r03 is confounded** (v1.8 → v1.9 directive AND T1–T3
  product, including the T2 skip on VW rung 1). No cross-round effect
  claims.
- Context scored (peak ctx/call); billing tabled, never verdict.
  The 10-call checkpoint is a leash, never a target.

## Tally (round-scoped)

TBD — filled as legs grade. Means + spreads, never single runs.
