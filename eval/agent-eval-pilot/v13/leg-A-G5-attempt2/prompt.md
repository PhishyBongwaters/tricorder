# Leg A-G5 attempt 2 — PROMPT (committed before launch, operator approval required)

- Model: default (me — same model as the pilot's A-legs). No override.
- Question ONLY (no keywords, no ground truth — the agent discovers terms):
  "Where does the Go compiler build SSA form for a function, and which
  function is the entry point?"
- Cap: 20 CLI calls, then answer with what you have.

---

## DIRECTIVE — v1, quoted verbatim from eval/agent-eval-pilot/DIRECTIVE.md
(as run: VW Q1–Q4, Go G1/G3/G5 — 10/10 legs ladder-compliant)

Escalation ladder, cheapest first, stop at the first rung that answers.
Hard cap 15 calls (20 on 10k+ file repos):

0. `--init` once (idempotent). Never `--wipe`, never `--diff`.
1. MAP: `--map-tokens 2048`. Visible answer → stop.
2. DETECT: `--detect "<query>" --format json --max-results 10`.
   1–2 wordings max.
3. SYMBOLS: `--symbols "<query>" --format json` for shapes.
4. READ exact lines: hit function body only, never whole files.
5. T1: `--tier 1 --context-lines 3`.
6. FULL FILE: last resort only.

Rules: `--format json` for machine steps; stay in target repo; final
answer cites file + line + symbol, every fact from a tool hit, no guesses.

## DIRECTIVE — v1.1 clarifications (verbatim, no behavior change)

- Read window: the hit function body (±15 lines is a floor, not a ceiling).
- Cold scans: prescan once per repo up front (sunk, uncharged, timed and
  recorded); legs run warm. Cold wall time is tracked, never scored.

## DIRECTIVE — v1.2 junk-hit retry (verbatim, from Go pilot cost data)

- After any detect whose hits are wrong-language or wrong-area, retry an
  exact symbol guess immediately; never read junk hits.

## DIRECTIVE — v1.3 query formulation (verbatim; under test this series)

- Exact symbol guess first, NL only as fallback. Guess the likeliest
  identifier before spending an NL query.
- Cap first passes: NL queries run with `--max-results 5`. Widen to 10
  only when the narrow pass returns nothing usable.

---

## HARNESS — this run only (not part of the directive)

- Target repo: `D:\Projects\Tricorder-Testing-Repos\go`
- CLI: `python
  C:\Users\macdo\AppData\Local\Temp\opencode\tricorder-fix-parallel-qualify\tricorder.py`
- Warm DB (prescanned 2026-09-23, sunk): always append
  `--db-path D:\Projects\Tricorder-Testing-Repos\bench_temp\eval-go-v13.db`
  to every CLI call. Run 0 (`--init`) is SKIPPED this leg — the DB is
  already built; `--init` would rebuild it. (Recorded deviation from v1.)
- Base shape: `python <CLI> --root <REPO> --db-path <DB> --format json
  <rung…>` (rung 1 MAP uses `--map-tokens 2048`; `--format json` on
  machine steps per v1 rules).
- READ rung = shell read of exact line ranges only (e.g.
  `sed -n '<a>,<b>p' <file>`); each invocation counts against the cap.
- Stay inside the target repo. No network, no installs.
- Final answer MUST cite file path + line + symbol/function name.

## RETURN (for the record)

1. Answer with citations.
2. Exact commands run, in order.
3. Per command: hit counts + whether it looked useful.
