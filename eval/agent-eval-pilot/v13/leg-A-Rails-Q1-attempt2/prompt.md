# Leg A-Rails-Q1 attempt 2 — PROMPT (committed before launch)

- Model: `llamacpp/Qwen` (local llama.cpp provider).
- Qwen re-run of attempt 1 under the frozen directive (v1–v1.6 + amended v1.3).
  Same question, same cap, same repo/DB. Qwen-everywhere program.
- Question ONLY (no keywords, no ground truth — the agent discovers terms):
  "How does ActiveRecord implement the `has_many` association and what methods does it generate?"
- Cap: 15 CLI calls, then answer with what you have.

---

## DIRECTIVE — v1, quoted verbatim from eval/agent-eval-pilot/DIRECTIVE.md
(as run: VW Q1–Q4, Go G1/G3/G5 — 10/10 legs ladder-compliant)

Escalation ladder, cheapest first, **STOP AT THE FIRST RUNG THAT ANSWERS**.
Hard cap 15 calls (20 on 10k+ file repos — this repo has ~4.5k source
files, so 15):

0. `--init` once (idempotent). Never `--wipe`, never `--diff`.
1. MAP: `--map-tokens 2048`. **Visible answer → STOP.**
2. DETECT: `--detect "<query>" --format json --max-results 10`.
   1–2 wordings max.
3. SYMBOLS: `--symbols "<query>" --format json` for shapes.
4. READ exact lines: hit function body only, never whole files.
5. T1: `--tier 1 --context-lines 3`. **Visible answer → STOP.**
6. FULL FILE: last resort only.

Rules: `--format json` for machine steps; stay in target repo; final
answer cites file + line + symbol, every fact from a tool hit, no guesses.
On huge repos use a per-leg `--db-path` (parallel legs must not share a DB)
and allow minutes for a cold scan — or better, run legs on a prescanned
warm DB (see below) and say so in the prompt.

## DIRECTIVE — v1.1 clarifications (verbatim, no behavior change)

- Read window: the hit function body (Q1's 100-line read covering two
  functions was fine; ±15 is a floor, not a ceiling).
- Cold scans: prescan once per repo up front (sunk, uncharged, timed and
  recorded); legs run warm. Cold wall time is tracked, never scored.

## DIRECTIVE — v1.2 junk-hit retry (verbatim, from Go pilot cost data)

- **Junk-hit retry:** After any detect whose hits are wrong-language or
  wrong-area, retry an exact symbol guess immediately; never read junk
  hits. Evidence: A-G5's failed NL query ("build SSA form for function")
  returned junk JS hits costing 58,624 tokens — 50× the leg's clean cost
  (1,093) and the costliest step in the pilot. Same crowding class as
  Swift Q4, at the query-formulation layer.

## DIRECTIVE — v1.3 query formulation (verbatim, as amended 2026-09-24)

- **Exact symbol guess first, NL only as fallback.** Every exact query in
  the pilot cost 150–1,150 tokens; every NL-first query risked five
  figures. Guess the likeliest identifier (`buildssa`, not "build SSA
  form for function") before spending an NL query.
- **Cap first passes:** ALL first-pass queries run with `--max-results 5`,
  exact or NL. Widen to 10 only when the narrow pass returns nothing
  usable. (Amended 2026-09-24: original text capped NL only; A-Vue-Q1
  attempt 3 showed exact guesses at 10 cost ~950 tok vs ~500 at 5.)

## DIRECTIVE — v1.4 read-window ceiling (verbatim rule)

- **Cap read windows:** one READ covers ONE function body, max ~120 lines.
  Two adjacent small functions in one window (the Q1 100-line precedent)
  is fine. Chaining sequential windows to walk a whole file is rung 6
  (FULL FILE) by another name — stop at the first window that answers.
- (Recorded deviation: v1.4's evidence paragraph is withheld from this
  prompt — it names the answer file from attempt 1. Rule above is verbatim.)

## DIRECTIVE — v1.5 one window per file (verbatim rule)

- **One read window per file.** A second window on the same file needs a
  locating grep first (in-file search or symbols hit naming the target
  symbol + line) — the grep IS the substitute. Elixir attempt 2 proved it:
  4 greps, 290 tok, zero blind second windows.
- Evidence: A-Vue-Q1 covered state.ts 1–200 and scheduler.ts 1–199 in
  chained ≤120-line pairs with no locating grep between windows. Per-call
  caps held; chaining persisted at ≤200-line scale. Recorded as minor
  exceedance, not fail.

## DIRECTIVE — v1.6 probe-first, MAP-last on small repos (verbatim)

- **Rung 0.5 — probe:** `--probe-digest` first (measured 64 tok on vue:
  language tally + file/line counts, no paths). Mandatory, unskippable,
  calibrates scale.
- **MAP-last under 1000 files:** when the probe shows <1000 code files,
  run ONE exact detect before MAP. If it names the answer file, SKIP MAP
  and proceed down the ladder; else run MAP as written. (Threshold from
  leg data: vue 466 / VW 506 / elixir 660 run small; rails 4470 / go
  12850 run map-first. VW won map-first — whether it wins map-last is an
  open re-run.)
- Evidence: both Vue A-legs paid 2,061 tok MAP-blind before knowing
  anything; capped exact detects then found everything at ~500 tok. The
  fixed MAP price dominates small-repo legs; v1.6 stops paying it blind.

---

## HARNESS — this run only (not part of the directive)

- Target repo: `D:\Projects\Tricorder-Testing-Repos\rails`
- CLI: `python
  C:\Users\macdo\AppData\Local\Temp\opencode\tricorder-fix-parallel-qualify\tricorder.py`
- Canonical warm DB (prescan 2026-09-23: 4,470/4,470 files, ranks live):
  run 0 (`--init`) is SKIPPED. Do NOT pass `--db-path` (resolves to the
  canonical DB automatically); do NOT rescan.
- **NEW: Use `--smart-map QUERY` instead of separate probe+detect+MAP.**
  Single call: probe → one exact detect → conditional MAP.
  - If detect finds exact match: skip MAP, output detect results.
  - If no exact match: fall through to full MAP.
- Base shape: `python <CLI> --root <REPO> --format json <rung…>`
  (`--format json` on machine steps per v1 rules).
- ALL first passes capped at `--max-results 5`; READ rung = shell read of
  exact line ranges only, ONE function body per read, max ~120 lines, ONE
  window per file unless a locating grep names the next target first; each
  invocation counts against the cap.
- Stay inside the target repo. No network, no installs.
- Final answer MUST cite file path + line + symbol/function name.

## RETURN (for the record)

1. Answer with citations.
2. Exact commands run, in order (full command lines with all flags).
3. Per command: hit counts + whether it looked useful.