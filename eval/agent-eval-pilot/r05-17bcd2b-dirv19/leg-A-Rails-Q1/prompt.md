# Leg A-Rails-Q1 — PROMPT (committed before launch, r05)

- Model: default (operator's model).
- Question ONLY (no keywords, no ground truth — discover terms yourself):
  "How does ActiveRecord implement the `has_many` association and what
  methods does it generate?"
- Cap: 15 tool calls, then answer with what you have. **Answer checkpoint
  at 10 calls** (see ladder rules).
- Target repo: `D:\Projects\Tricorder-Testing-Repos\rails`
  (~3,500 source files).
- Tricorder code: `main` @ `17bcd2b`. Warm canonical DB (settled).
- On EVERY tricorder call pass BOTH
  `--root D:\Projects\Tricorder-Testing-Repos\rails` AND
  `--db-path D:\Projects\tricorder\.tricorder\db\rails.db` — no
  exceptions. NEVER `--wipe`, NEVER `--diff`.
- Tricorder CLI: `D:\Projects\tricorder\tricorder.py` via
  `.venv/Scripts/python.exe`. Shell is PowerShell. Stay in target repo.
  `--format json` for machine steps.
- NEVER issue the identical tool call twice in a row. If 3 consecutive
  tool results do not advance you toward an answer file/symbol, STOP
  searching and answer with what you have.

## Ladder — v1.9 for an under-5000 repo (quoted from DIRECTIVE.frozen.md)

0. `--init` once (idempotent).
0.5. `--probe-digest` first (scale calibration, unskippable).
1. `--smart-map "<IDENTIFIER>"` — rung 1 takes an IDENTIFIER, never the
   question. Derive the likeliest identifier first (backticked spans, then
   `Class::method` / `snake_case` / `camelCase`, length ≥ 3). Exact hit →
   MAP skipped, proceed down the ladder; else MAP as written
   (`--map-tokens 2048` if MAP runs).
2. DETECT: `--detect "<query>" --format json --max-results 5`.
   1–2 wordings max. Exact symbol guess first, NL only as fallback.
   After any detect whose hits are wrong-language or wrong-area, retry
   an exact symbol guess immediately; never read junk hits, never
   re-issue a junk query.
3. SYMBOLS: `--symbols "<query>" --format json --max-results 5`.
4. BODY READ at the cited line: ONE function body, max ~120 lines. Rung 4
   is not "read around" — open the window that CONTAINS the line a tool
   already reported. Never walk toward a line: no creeping windows, no
   re-reading ground an earlier window covered. If the cited line is a
   doc comment, the next window contains the def it documents.
   Doc-walk ban: reads are for code, not prose. A window that returns
   only comments is a FAILED rung-4 call — go back to the tool, never
   forward through the file.
5. T1: `--tier 1 --context-lines 3`.
5.5. MAP fallback (only if rungs 2–5 failed).
6. FULL FILE: last resort only. No chained windows; a second window on
   the same file needs a locating grep first.

Leash: at 10 of your 15 calls, STOP searching and answer with what you
have. The checkpoint is a termination leash, not a target.

Rules: final answer cites file + line + symbol, every fact from a tool
hit, no guesses.

## Bookkeeping: NONE

Save NOTHING to disk (no step files, no transcript). Every call and
result is logged harness-side. Finish with your answer + cites, then
report back: answer, calls used.
