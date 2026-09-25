# Leg A-VW-Q1 — PROMPT (committed before launch, operator approval required)

- Model: default (operator's model).
- Question ONLY (no keywords, no ground truth — discover terms yourself):
  "Where is TOTP two-factor code verification implemented?"
- Cap: 15 tool calls, then answer with what you have.
- Target repo: `D:\Projects\Tricorder-Testing-Repos\vaultwarden`
  (~506 source files).
- Tricorder code: `main` @ `46d32c1`. Warm canonical DB (settled).
- On EVERY tricorder call pass BOTH
  `--root D:\Projects\Tricorder-Testing-Repos\vaultwarden` AND
  `--db-path D:\Projects\tricorder\.tricorder\db\vaultwarden.db` — no
  exceptions. NEVER `--wipe`, NEVER `--diff`.
- Tricorder CLI: `D:\Projects\tricorder\tricorder.py` via
  `.venv/Scripts/python.exe`. Shell is PowerShell. Stay in target repo.
  `--format json` for machine steps.
- NEVER issue the identical tool call twice in a row. If 3 consecutive
  tool results do not advance you toward an answer file/symbol, STOP
  searching and answer with what you have.

## Ladder — v1.8 for an under-5000 repo (quoted from DIRECTIVE.frozen.md)

0. `--init` once (idempotent).
0.5. `--probe-digest` first (scale calibration, unskippable).
1. `--smart-map "QUERY"` (probe + ONE exact detect + conditional MAP).
   Exact hit → MAP skipped, proceed down the ladder; else MAP as
   written (`--map-tokens 2048` if MAP runs).
2. DETECT: `--detect "<query>" --format json --max-results 5`.
   1–2 wordings max. Exact symbol guess first, NL only as fallback.
   After any detect whose hits are wrong-language or wrong-area, retry
   an exact symbol guess immediately; never read junk hits, never
   re-issue a junk query.
3. SYMBOLS: `--symbols "<query>" --format json --max-results 5`.
4. READ exact lines: ONE function body, max ~120 lines. Stop at the
   first window that answers.
5. T1: `--tier 1 --context-lines 3`.
5.5. MAP fallback (only if rungs 2–5 failed).
6. FULL FILE: last resort only. No chained windows; a second window on
   the same file needs a locating grep first.

Rules: final answer cites file + line + symbol, every fact from a tool
hit, no guesses.

## Bookkeeping: NONE

Save NOTHING to disk (no step files, no transcript). Every call and
result is logged harness-side. Finish with your answer + cites, then
report back: answer, calls used.
