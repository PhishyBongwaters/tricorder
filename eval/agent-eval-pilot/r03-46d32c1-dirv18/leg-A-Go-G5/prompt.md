# Leg A-Go-G5 — PROMPT (committed before launch, operator approval required)

- Model: default (operator's model — same vehicle as the tight v13 legs).
- Question ONLY (no keywords, no ground truth — discover terms yourself):
  "Where does the Go compiler build SSA form for a function, and which
  function is the entry point?"
- Cap: 20 tool calls, then answer with what you have.
- Target repo: `D:\Projects\Tricorder-Testing-Repos\go` (~12,850 files).
- Tricorder code: `main` @ `46d32c1`. Warm canonical DB (settled).
- On EVERY tricorder call pass BOTH
  `--root D:\Projects\Tricorder-Testing-Repos\go` AND
  `--db-path D:\Projects\tricorder\.tricorder\db\go.db` — no exceptions
  (the CLI defaults to the working directory, which is the WRONG repo).
  NEVER `--wipe`, NEVER `--diff`.
- Tricorder CLI: `D:\Projects\tricorder\tricorder.py` via
  `.venv/Scripts/python.exe`. Shell is PowerShell. Stay in target repo.
  `--format json` for machine steps.
- NEVER issue the identical tool call twice in a row: if a result does
  not advance you, change the query (new terms, narrower scope) or move
  to the next rung. Repeating a call that returned junk is failure.

## Ladder — v1.8 for a 5000+ file repo (quoted from DIRECTIVE.frozen.md)

Repo exceeds 5000 code files → SKIP rung-1 MAP, open at rung 2:

2. DETECT: `--detect "<query>" --format json --max-results 5`.
   1–2 wordings max. Exact symbol guess first, NL only as fallback.
   After any detect whose hits are wrong-language or wrong-area, retry
   an exact symbol guess immediately; never read junk hits, never
   re-issue a junk query.
3. SYMBOLS: `--symbols "<query>" --format json --max-results 5`.
4. READ exact lines: ONE function body, max ~120 lines. Stop at the
   first window that answers.
5. T1: `--tier 1 --context-lines 3`.
5.5. MAP (fallback only): `--map-tokens 2048` — available because
   rungs 2–5 failed, never as an opener here.
6. FULL FILE: last resort only. No chained windows; a second window on
   the same file needs a locating grep first.

Rules: final answer cites file + line + symbol, every fact from a tool
hit, no guesses.

## Bookkeeping: NONE

Save NOTHING to disk (no step files, no transcript). Every call and
result is logged harness-side. Finish with your answer + cites, then
report back: answer, calls used.
