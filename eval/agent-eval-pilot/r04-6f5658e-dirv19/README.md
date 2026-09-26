# Round r04 — directive v1.9 on the post-rebuild build (4 legs)

## Build (frozen)

- **Code**: `6f5658e` (text-mode `--smart-map` skip KeyError fix on top
  of `81229f8` T1 mechanism-2 — operator-ratified amendment: the
  non-JSON skip branch read `s["type"]` (symbols field) on detect-family
  hits and crashed every identifier skip; JSON/MCP unaffected. Suite
  531 green on the frozen content). T1 `bba4a58` / T2 `144aa54` / T3
  `47e57a8` are all in this build.
- **Directive**: v1.9, frozen at `DIRECTIVE.frozen.md` (copy of
  `../DIRECTIVE.md` at freeze time). v1.9 = identifier-input rung 1,
  rung 4 named by mechanism, doc-walk ban, 10-call answer checkpoint.
- **Why a new round and not r03-continued**: the r03 stop-the-line rule
  ("either moving starts a new round") fired — code moved (T1/T2/T3) and
  the Rails canonical DB was rebuilt. r03 closes at 5/12 legs scored;
  its legs stand as run. This is a derivation from the frozen rule, not
  a re-scope of r03: no r03 leg is voided, re-scored, or moved here.
- **Repo revisions**: rails `8d07fafa44` (2026-08-25), vaultwarden
  `0cefa4cc` (2026-08-07).
- **DBs**: canonical `.tricorder/db/{rails,vaultwarden}.db`, warm-verified
  at freeze (sunk, uncharged): rails probe 0.59s / detect 2.85s, 3509
  code files (post-T1+mechanism-2, was 4470 pre-T1); vaultwarden probe
  0.36s / detect 0.48s, 421 code files. `file_state` 3931 / 504, `meta`
  1 row each, `file_ranks` 3455 fresh (rails).

## Vehicle + metering

- **Vehicle**: subagents on the operator's model (default — no `model`
  arg), fresh context per leg, question text only. Same vehicle as r03's
  five scored legs so the directive change is the only intended
  difference.
- **Metering**: harness truth — `opencode.db` session rows
  (`session_v2` input/output/cache_read, `session_message` for the tool
  trail). Provider-native units. Agents save NOTHING; grades are audited
  from message contents, never self-report.
- One foreground subagent at a time. Prompts committed before launch.

## Legs (4)

| # | Leg | Question | Session | Status |
|---|---|---|---|---|
| 1 | A-Rails-Q1 | `has_many` | — | pending |
| 2 | B-Rails-Q1 | `has_many` (grep only) | — | pending |
| 3 | A-VW-Q1 | TOTP verification | — | pending |
| 4 | B-VW-Q1 | TOTP verification (grep only) | — | pending |

Scope rationale: VW-Q1 and Rails-Q1 are the two pairs where r03 has a
scored A and B (A/B 0.50× on VW-Q1) and where the v1.9 evidence lives
(Rails = the doc-walk; VW = the prose-at-rung-1 miss pair). Go-G5 is the
round's control elsewhere: 3 calls, 12,515, one read — there is nothing
left for three of the four v1.9 items to bite on, so it is held back
rather than spent here.

## What this round can and cannot show

- **VW pair is a clean directive-vs-directive comparison** against r03
  (A 14,743 / B 29,200): the vaultwarden DB was not touched by T1–T3 and
  the MAP bytes were verified identical, so the build difference is the
  directive text only.
- **Rails pair is CONFOUNDED and must be read as such.** r03 A-Rails-Q1
  (25,289) ran on the pre-T1 DB and pre-T2/T3 rung behavior; this leg
  runs on the rebuilt DB (3509 code files, T2 identifier-first skip,
  T3 definition-site-first symbols). A delta there is directive + product
  + DB, not directive alone. Stated here so the tally cannot be quoted
  as a directive effect.
- **The four v1.9 items ship bundled**, so per-item effect is not
  attributable even where the comparison is clean. r04 tests the bundle.
- Token savings is the only scored metric. The 10-call checkpoint is a
  termination leash, never a target.

## Judgment calls (agent-made, operator-revocable)

The operator dismissed the pre-launch scope question, so these were taken
by default rather than confirmed. Any of them can be voided by the
operator; nothing here re-scores or re-claims an earlier round.

1. r04 rather than r03-continued (forced by the stop-the-line rule; see
   Build).
2. All four buildable v1.9 items in one version (the fifth, the
   harness-side loop breaker, is not buildable in this repo).
3. Four legs (A+B on VW-Q1 and Rails-Q1) rather than the full twelve.
4. Operator-model vehicle, as in r03.

## Tally (round-scoped)

TBD — filled as legs grade. Tokens only.
