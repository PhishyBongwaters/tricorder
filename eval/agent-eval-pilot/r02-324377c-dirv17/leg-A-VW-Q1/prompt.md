# Leg A-VW-Q1 — PROMPT (committed before launch, operator approval required)

- Model: `llamacpp/Qwen` (local llama.cpp provider, `Qwen3.6-35B-A3B-UD-Q4_K_M.gguf`).
- Question ONLY (no keywords, no ground truth — the agent discovers terms):
  "Where is TOTP two-factor code verification implemented?"
- Cap: 15 CLI calls, then answer with what you have.
- Target repo: `D:\Projects\Tricorder-Testing-Repos\vaultwarden`
  (~506 source files, so cap 15).
- Tricorder code: `main` @ `324377c` (directive v1.7 + serve-perf fixes).
- Warm DB: `.tricorder/db/vaultwarden.db` (canonical, settled — prescan
  sunk, uncharged). Pass `--db-path D:\Projects\tricorder\.tricorder\db\vaultwarden.db`
  on every tricorder call. Settle MAP timed 3s steady.
- Stay in the target repo. `--format json` for machine steps.
- Save every tool result payload to `step_<name>.txt` in this folder and
  maintain `transcript.md` (cmd, step, result summary). Final answer must
  cite file + line + symbol, every fact from a tool hit, no guesses.

---

## DIRECTIVE — v1.7, quoted verbatim from
## `eval/agent-eval-pilot/r02-324377c-dirv17/DIRECTIVE.frozen.md`

Escalation ladder, cheapest first, stop at the first rung that answers.
Hard cap 15 calls (20 on 10k+ file repos):

0. `--init` once (idempotent). Never `--wipe`, never `--diff`.
0.5. `--probe-digest` first (language tally + file/line counts, no
paths). Mandatory, unskippable, calibrates scale.
1. `--smart-map "QUERY"` (probe + ONE exact detect + conditional MAP).
Under 5000 files: exact hit → MAP skipped, proceed down the ladder;
else MAP as written. Over threshold → straight to MAP. `--map-tokens`
honored (`--map-tokens 2048` if MAP runs).
2. DETECT: `--detect "<query>" --format json --max-results 5`.
1–2 wordings max. Exact symbol guess first, NL only as fallback.
3. SYMBOLS: `--symbols "<query>" --format json --max-results 5` for shapes.
4. READ exact lines: ONE function body, max ~120 lines. Stop at the
first window that answers.
5. T1: `--tier 1 --context-lines 3`.
6. FULL FILE: last resort only. Chaining sequential windows to walk a
whole file is rung 6 by another name. A second window on the same file
needs a locating grep first.

Rules: `--format json` for machine steps; stay in target repo; final
answer cites file + line + symbol, every fact from a tool hit, no
guesses. After any detect whose hits are wrong-language or wrong-area,
retry an exact symbol guess immediately; never read junk hits.
