# Leg A-Elixir-Q1 attempt 1 — GRADE (Qwen model)

## Verdict: PASS — **ladder NON-compliant (rung-4 overbreadth)**

Answer correct: GenServer file, all 8 callbacks, init-only-required,
`use`-injected defaults, `:gen_server` delegation, `$gen_call`/`$gen_cast`
protocol — all verified against ground truth
(`gen_server.ex`: `@callback handle_call` :647, `def start_link` :1077,
`def call` :1172, `:gen.start(:gen_server` :1094). 9/15 calls.

## Tokens

| Step | Tokens | Note |
|---|---|---|
| MAP 2048 | 2,079 | kernel.ex tags only — noise |
| detect "GenServer" (10) | 982 | top hit gen_server.ex:5 |
| symbols "GenServer" | 499 | 4 modules, confirmed 5–1376 |
| detect "callback" (10) | 1,050 | cross-area, unread |
| reads 5 × 200–300 lines | 12,747 | whole file 1–1376 in chunks |
| **Total** | **17,357** | reads = 73% |

## Compliance

- Order MAP → DETECT → SYMBOLS → DETECT → READ ×5 follows the ladder;
  `--format json` on machine steps; in-repo; no `--db-path`; rung 0 skipped.
- **Violation (rung 4):** "READ exact lines: hit function body only, never
  whole files." Steps 5–9 read the entire 1,376-line file cover-to-cover in
  200/300-line windows instead of stopping at the first answer (steps 2–3
  had already identified the file + module span) and dropping to
  symbol-guided exact reads (`handle_call`, `call`, `start_link`,
  `__using__`). 12,747 of 17,357 tokens.
- Minor: 2nd detect `"callback"` is generic/NL-ish at `--max-results 10`;
  v1.3 caps NL first passes at 5. Agent showed good v1.2 discipline by not
  reading the cross-area hits.
- Qwen's first compliance fail in the series (was 4/4 perfect); over-read
  pattern previously Nemotron-only.

## Model Tracking

| Leg | Model | Provider |
|---|---|---|
| A-Elixir-Q1 | **Qwen** | **llamacpp** |
| A-VW-Q3/Q4, A-G1-Qwen, A-Rails-Q1 | Qwen | llamacpp |
| All other v1.3 A-legs | Nemotron | opencode |

## Findings

1. **MAP rung noise again (4th data point).** Elixir MAP: 2,079 tok, 38 tags,
   one file (`kernel.ex`) — answer file absent. Go: dead; VW/Rails: noise;
   elixir: noise. Exact-first symbols bypass it everywhere.
2. **Linear-read gravity.** Once symbols identified the single answer file,
   the agent read it end-to-end instead of narrowing. Rung-4 "function body
   only" loses to whole-file momentum on single-file answers — candidate
   for stronger directive wording (a future v1.4 question, NOT this series).
3. **Answer needed no T1/full-file** — reads sufficed; ladder depth was fine,
   breadth was not.
