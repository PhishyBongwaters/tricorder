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

## Legs (6 — three runs per arm)

| # | Leg | Question | Session | Status |
|---|---|---|---|---|
| 1 | A-VW-Q1-run1 | TOTP verification | — | pending |
| 2 | A-VW-Q1-run2 | TOTP verification | — | pending |
| 3 | A-VW-Q1-run3 | TOTP verification | — | pending |
| 4 | B-VW-Q1-run1 | TOTP verification (grep only) | — | pending |
| 5 | B-VW-Q1-run2 | TOTP verification (grep only) | — | pending |
| 6 | B-VW-Q1-run3 | TOTP verification (grep only) | — | pending |

Scope rationale (operator-ordered): single-run cache-luck noise
measured ±10k input on r05 A — same order as close-pair gaps. n=3
per arm (≈5.8k SE) resolves 7k+ gaps directionally. A-arm runs first
(rung order), then B.

## What this round can and cannot show

- **r06 A/B pair is contemporary** (same build/DB/directive/vehicle):
  the only valid VW score. Means quoted with run spread, never single
  runs.
- **r06-vs-r03 is confounded** (v1.8 → v1.9 directive AND T1–T3
  product, including the T2 skip on VW rung 1). No cross-round effect
  claims.
- Token primary scored; context-differential tabled in every grade.
  The 10-call checkpoint is a leash, never a target.

## Tally (round-scoped)

TBD — filled as legs grade. Means + spreads, never single runs.
