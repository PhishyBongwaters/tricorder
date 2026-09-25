# Round r02 — fresh A/B, 1 Q per repo (6 repos, 12 legs)

- **Build**: code `324377c` + directive v1.7 (frozen copy:
  `DIRECTIVE.frozen.md`). Either moving starts a new round (stop-the-line).
- **Model**: local `llamacpp/Qwen`, file `Qwen3.6-35B-A3B-UD-Q4_K_M.gguf`
  (16GB VRAM class — the optimization target). One foreground subagent
  per leg. No skills loaded.
- **Meter**: `v13/meter_leg.py`, tiktoken cl100k, agent-visible
  result-payload tokens; directive text excluded; wall-clock not scored.
- **Questions**: `../QUESTIONS.md` canonical six. Ground truths frozen
  there; legs cite file + line + symbol.
- **DBs**: canonical `.tricorder/db/<repo>.db`, settled in setup below
  (sunk, uncharged). A-legs share canonical DBs sequentially; B-legs
  use grep/read/glob only (no DB).

## Setup (sunk prescan/settle — recorded, uncharged)

| Repo | DB status at round start |
|---|---|
| vaultwarden | backfilled 2026-09-25 (29k refs, 93 ranks — thin vs 506 files; watch coverage at leg 1), settled 3s steady |
| go | backfilled 2026-09-25 (10,736 ranks), settled: 289s → 6s steady |
| rails | backfilled 2026-09-25 (3,490 ranks), settled: 85s → 2s steady |
| elixir | backfilled 2026-09-25 (1M refs, 613 ranks), settled 19s steady |
| vue | backfilled 2026-09-25 (29k refs, 402 ranks), settled 3s steady |
| swift | backfilled 2026-09-25 (13.5M refs, 24,840 ranks, 477s), settled: 1424s drift rescan → 13s steady |

## Legs

| # | Leg | Question | Status |
|---|---|---|---|
| 1 | A-VW-Q1 | TOTP verification | PASS, 5 calls, 634 tok (minor: 219-line full read) |
| 2 | B-VW-Q1 | TOTP verification (grep only) | TODO |
| 3 | A-Go-G5 | SSA build entry | TODO |
| 4 | B-Go-G5 | SSA build entry (grep only) | TODO |
| 5 | A-Rails-Q1 | has_many | TODO |
| 6 | B-Rails-Q1 | has_many (grep only) | TODO |
| 7 | A-Elixir-Q1 | GenServer | TODO |
| 8 | B-Elixir-Q1 | GenServer (grep only) | TODO |
| 9 | A-Vue-Q1 | reactivity | TODO |
| 10 | B-Vue-Q1 | reactivity (grep only) | TODO |
| 11 | A-Swift-Q1 | expression parser | TODO |
| 12 | B-Swift-Q1 | expression parser (grep only) | TODO |

## Tally (grand — round-scoped, never mixed across builds)

TBD — filled as legs grade.
