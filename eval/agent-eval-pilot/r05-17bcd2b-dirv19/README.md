# Round r05 — Rails pair re-run on the T4 build (2 legs)

## Build (frozen)

- **Code**: `17bcd2b` (T4: symbols rescue-hit ranking). Directive
  unchanged: v1.9, frozen at `DIRECTIVE.frozen.md` (byte-copy of the
  r04 freeze).
- **Why a new round and not r04-continued**: the stop-the-line rule
  fired again — product code moved (T4 touches the symbols rescue path
  the r04 A-leg actually exercised at call 7) after r04 legs 1–2
  scored. r04 stands as run (Rails pair 0.72× inversion recorded
  there). This is a derivation from the frozen rule, not a re-scope:
  no r04 leg is voided, re-scored, or moved here.
- **DBs**: canonical `.tricorder/db/rails.db` untouched by T4
  (code-only sort change; no rescan needed). Warm-verified: `file_state`
  3931, `meta` 1 row, `file_ranks` 3455 fresh.

## Vehicle + metering

- **Vehicle**: subagents on the operator's model (default — no `model`
  arg), fresh context per leg, question text only. Same as r04.
- **Metering**: harness truth (`opencode.db` session rows). Agents save
  NOTHING; grades audited from message contents.
- One foreground subagent at a time. Prompts committed before launch.

## Legs (2)

| # | Leg | Question | Session | Status |
|---|---|---|---|---|
| 1 | A-Rails-Q1 | `has_many` | `ses_f22250609ffeM1mr4xrpMX0MFx` | PASS 10 calls, 29,909 (grade.md) |
| 2 | A-Rails-Q1-run2 | `has_many` | `ses_f221a4ca5ffeLAv4NLCTmDyS3P` | PASS 10 calls, 18,439, peak 17,450 (grade.md) |
| 3 | A-Rails-Q1-run3 | `has_many` | — | pending |
| 4 | B-Rails-Q1-run1 (r04) | `has_many` (grep only) | `ses_f2234e894ffed1p7J3W8YJOYmu` | PASS 15 calls, 25,466 (r04 grade) |
| 5 | B-Rails-Q1-run2 | `has_many` (grep only) | — | pending |
| 6 | B-Rails-Q1-run3 | `has_many` (grep only) | — | pending |

Repeat rationale (operator-ordered): single-run cache noise ±10k —
n=3/arm for means. B-run1 adopted from r04 (grep-only, code-invariant).
| 2 | B-Rails-Q1 | `has_many` (grep only) | — | pending |

Scope rationale: re-run the Rails pair on the T4 build. The A-arm is
the measurement (r04 A call 7 hit the exact rescue path T4 changed).
The B-arm touches no tricorder code path — expected invariant vs r04
B (25,466); re-run keeps the pair contemporaneous and checks baseline
stability. VW pair NOT re-run (T4's rescue-order change could in
principle move VW symbols outputs, but the VW legs never fired rescue
on their recorded trails — out of scope unless the operator orders).

## What this round can and cannot show

- **A r05-vs-r04 delta is product-only** (same directive v1.9, same
  DB, same vehicle): attributable to T4 where the trail shows rescue
  hits, nowhere else.
- **B r05-vs-r04 delta should be ~zero** (same question, same repo, no
  code path). Any large move is agent noise or repo drift, not product.
- Token savings is the only scored metric. The 10-call checkpoint is a
  termination leash, never a target.

## Tally (round-scoped)

TBD — filled as legs grade. Tokens only.
