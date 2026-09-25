# Agent-eval directive (CLI-first)

Versioned prompt for tricorder legs. B-legs get the baseline prompt instead
(same question, same cap, grep/read/glob only, stay in target repo).

## v1 (as run: VW Q1–Q4, Go G1/G3/G5 — 10/10 legs ladder-compliant)

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
On huge repos use a per-leg `--db-path` (parallel legs must not share a DB)
and allow minutes for a cold scan — or better, run legs on a prescanned
warm DB (see below) and say so in the prompt.

## v1.1 (clarifications, no behavior change)

- Read window: the hit function body (Q1's 100-line read covering two
  functions was fine; ±15 is a floor, not a ceiling).
- Cold scans: prescan once per repo up front (sunk, uncharged, timed and
  recorded); legs run warm. Cold wall time is tracked, never scored.

## v1.2 (new rule from Go pilot cost data)

- **Junk-hit retry:** after any detect whose hits are wrong-language or
  wrong-area, retry an exact symbol guess immediately; never read junk
  hits. Evidence: A-G5's failed NL query ("build SSA form for function")
  returned junk JS hits costing 58,624 tokens — 50× the leg's clean cost
  (1,093) and the costliest step in the pilot. Same crowding class as
  Swift Q4, at the query-formulation layer.

## v1.3 (query formulation: exact-first, capped first passes)

- **Exact symbol guess first, NL only as fallback.** Every exact query in
  the pilot cost 150–1,150 tokens; every NL-first query risked five
  figures. Guess the likeliest identifier (`buildssa`, not "build SSA
  form for function") before spending an NL query.
- **Cap first passes:** ALL first-pass queries run with `--max-results 5`,
  exact or NL. Widen to 10 only when the narrow pass returns nothing
  usable. (Amended 2026-09-24: original text capped NL only; A-Vue-Q1
  attempt 3 showed exact guesses at 10 cost ~950 tok vs ~500 at 5. Prior
  legs quoted the original verbatim and stand as run.)

## v1.4 (read-window ceiling; closes the v1.1 loophole)

- **Cap read windows:** one READ covers ONE function body, max ~120 lines.
  Two adjacent small functions in one window (the Q1 100-line precedent)
  is fine. Chaining sequential windows to walk a whole file is rung 6
  (FULL FILE) by another name — stop at the first window that answers.
- Evidence: A-Elixir-Q1 read gen_server.ex 1–1376 in five 200–300-line
  windows (12,747 of 17,357 tokens, 73%) after rungs 2–3 had already
  identified the file. Literal v1.1 ("a floor, not a ceiling") permitted
  it; rung-4 intent forbade it. Leg keeps its compliance-fail tag.

## v1.5 (one window per file; grep justifies the second)

- **One read window per file.** A second window on the same file needs a
  locating grep first (in-file search or symbols hit naming the target
  symbol + line) — the grep IS the substitute. Elixir attempt 2 proved it:
  4 greps, 290 tok, zero blind second windows.
- Evidence: A-Vue-Q1 covered state.ts 1–200 and scheduler.ts 1–199 in
  chained ≤120-line pairs with no locating grep between windows. Per-call
  caps held; chaining persisted at ≤200-line scale. Recorded as minor
  exceedance, not fail.

## v1.6 (probe-first; MAP-last on small repos)

- **Rung 0.5 — probe:** `--probe-digest` first (measured 64 tok on vue:
  language tally + file/line counts, no paths). Mandatory, unskippable,
  calibrates scale.
- **MAP-last under 1000 files:** when the probe shows <1000 code files,
  run ONE exact detect before MAP. If it names the answer file, SKIP MAP
  and proceed down the ladder; else run MAP as written. (Threshold from
  leg data: vue 466 / VW 506 / elixir 660 run small; rails 4470 / go
  12850 run map-first. VW won map-first — whether it wins map-last is an
  open re-run.)

## v1.7 (smart-map rung; reconciles v1.6 with the tool)

- **Rung 1 is `--smart-map "QUERY"`** (v1.6's probe + ONE exact detect +
  conditional MAP, now one flag on CLI and MCP alike). Under
  `SMART_MAP_MAX_FILES=5000` files: exact hit → MAP skipped, proceed
  down the ladder; else MAP as written. Over threshold → straight to
  MAP. `--map-tokens` honored on the CLI leg.
- v1.6's "<1000 files" text is superseded: the threshold was raised to
  5000 to cover Rails (4470 files). Legs run under v1.6 quoted it
  verbatim and stand as run; v1.7 legs quote this version.
- Unchanged: ladder order, 15/20-call caps, `--max-results 5` first
  passes, 120-line read ceiling, one-window-per-file + locating grep,
  `--format json` for machine steps, citation discipline, per-leg
  `--db-path`, warm-DB setup stated in the prompt.
- Evidence: both Vue A-legs paid 2,061 tok MAP-blind before knowing
  anything; capped exact detects then found everything at ~500 tok. The
  fixed MAP price dominates small-repo legs; v1.6 stops paying it blind.
