# Arm M (map-first) — PROMPT (committed before launch)

- Model: `llamacpp/Qwen` (local, `Qwen3.6-35B-A3B-UD-Q4_K_M.gguf`).
- Question ONLY (no keywords, no ground truth — discover terms yourself):
  "Where does the Go compiler build SSA form for a function, and which
  function is the entry point?"
- Cap: 20 tool calls, then answer with what you have.
- Target repo: `D:\Projects\Tricorder-Testing-Repos\go`. Warm canonical
  DB: pass `--db-path D:\Projects\tricorder\.tricorder\db\go.db` on every
  tricorder call. NEVER `--wipe`, NEVER `--diff`.
- Tricorder CLI: `D:\Projects\tricorder\tricorder.py` via
  `.venv/Scripts/python.exe`. Shell is PowerShell. Stay in target repo.
  `--format json` for machine steps.

## Ladder (map-first arm — follow exactly)

Cheapest first, stop at the first rung that answers:

0. `--init` once (idempotent).
0.5. `--probe-digest` first (scale calibration, unskippable).
1. MAP (MANDATORY, no skipping): `--map-tokens 2048`. Visible answer → stop.
2. DETECT: `--detect "<query>" --format json --max-results 5`. 1–2
   wordings max. Exact symbol guess first, NL only as fallback.
3. SYMBOLS: `--symbols "<query>" --format json --max-results 5`.
4. READ exact lines: ONE function body, max ~120 lines. Stop at the
   first window that answers.
5. T1: `--tier 1 --context-lines 3`.
6. FULL FILE: last resort only. No chained windows; a second window on
   the same file needs a locating grep first.

Rules: final answer cites file + line + symbol, every fact from a tool
hit, no guesses. After any detect whose hits are wrong-language or
wrong-area, retry an exact symbol guess immediately; never read junk.

## Bookkeeping: NONE

Do NOT save step files. Do NOT maintain a transcript. Every call and
result is logged harness-side. Finish with your answer + cites, then
report back: answer, calls used.
