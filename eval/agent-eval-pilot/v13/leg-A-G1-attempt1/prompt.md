# Leg A-G1 attempt 1 — PROMPT (committed before launch, operator approval required)

- Model: default (me — same model as the pilot's A-legs). No override.
- Question ONLY (no keywords, no ground truth — the agent discovers terms):
  "Where is the Go garbage collector's mark phase implemented, and what
  function do the background mark workers run?"
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
- Canonical warm DB (full prescan 2026-09-23, 12,850/12,850 files, ranks
  live — recorded in `v13/RUNLOG.md`): run 0 (`--init`) is SKIPPED, the
  DB is already built. Do NOT pass `--db-path` (resolves to the canonical
  DB automatically); do NOT rescan. (Recorded deviation from v1.)
- MAP rung 1 runs AS WRITTEN (`--map-tokens 2048`, explicit floor
  budget): file_ranks are live since the prescan, so the rung that timed
  out in A-G5 may now answer. If it times out again, move on — the
  timeout itself is a graded finding.
- Base shape: `python <CLI> --root <REPO> --format json <rung…>`
  (`--format json` on machine steps per v1 rules).
- READ rung = shell read of exact line ranges only (e.g.
  `sed -n '<a>,<b>p' <file>`); each invocation counts against the cap.
- Stay inside the target repo. No network, no installs.
- Final answer MUST cite file path + line + symbol/function name.

## RETURN (for the record)

1. Answer with citations.
2. Exact commands run, in order.
3. Per command: hit counts + whether it looked useful.
