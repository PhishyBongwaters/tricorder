# Round r03 — operator-model legs on current build (12 legs)

- **Build**: code `46d32c1` (serve-perf fixes + rescue keyword strip) +
  directive v1.8 (frozen copy: `DIRECTIVE.frozen.md`). Either moving
  starts a new round (stop-the-line).
- **Vehicle**: subagents on the operator's model (default,
  muse-spark — the model that ran the tight v13 legs). Qwen local
  demonstrated catastrophic looping (map-vs-detect arm M: 212 tools,
  150× identical query); parked until a harness loop guard exists.
- **Blindness**: fresh subagent context per leg, question text only —
  same blindness guarantee as prior rounds.
- **Metering**: harness session rows (`opencode.db`), input+output
  primary, cache alongside. Agents save NOTHING (no step files, no
  transcript) — audit from the session log. Session IDs recorded per
  leg below.
- **Questions**: `../QUESTIONS.md` canonical six. Ground truths frozen
  there; legs cite file + line + symbol.
- **DBs**: canonical `.tricorder/db/<repo>.db`, settled 2026-09-25.
  Sequential legs share canonical DBs; B-legs use grep/read/glob only.

## Legs

| # | Leg | Question | Session | Status |
|---|---|---|---|---|
| 1 | A-Go-G5 | SSA build entry | `ses_f269d99b9ffeqTou5sce4vDrOS` | PASS, 3 calls, 12,515 (in+out) |
| 2 | B-Go-G5 | SSA build entry (grep only) | `ses_f269ba64affeV2v4Zt8TS2TEXP` | PASS, 5 calls, 20,781 (in+out); A/B 0.60× |
| 3 | A-VW-Q1 | TOTP verification | `ses_f2692da5affemV4XzikqhxeKcb` | PASS, 7 calls, 14,743 (in+out) |
| 4 | B-VW-Q1 | TOTP verification (grep only) | `ses_f26912729ffeiPLMwJVeDGoh7b` | PASS, 3 calls, 29,200 (in+out); A/B 0.50× |
| 5 | A-Rails-Q1 | has_many | TODO | TODO |
| 6 | B-Rails-Q1 | has_many (grep only) | TODO | TODO |
| 7 | A-Elixir-Q1 | GenServer | TODO | TODO |
| 8 | B-Elixir-Q1 | GenServer (grep only) | TODO | TODO |
| 9 | A-Vue-Q1 | reactivity | TODO | TODO |
| 10 | B-Vue-Q1 | reactivity (grep only) | TODO | TODO |
| 11 | A-Swift-Q1 | expression parser | TODO | TODO |
| 12 | B-Swift-Q1 | expression parser (grep only) | TODO | TODO |

## Tally (round-scoped)

TBD — filled as legs grade. Tokens only.
