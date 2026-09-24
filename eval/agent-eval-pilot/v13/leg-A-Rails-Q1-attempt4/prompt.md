# Leg A-Rails-Q1 attempt 4 — PROMPT (committed before launch)

- Model: `llamacpp/Qwen` (local llama.cpp provider).
- Qwen re-run with **strict adherence** to constraints.
- Same question, same cap, same repo/DB.
- Question ONLY (no keywords, no ground truth):
  "How does ActiveRecord implement the `has_many` association and what methods does it generate?"
- Cap: **15 TOTAL operations** (CLI + shell reads combined), then answer.

---

## DIRECTIVE — v1–v1.6 (frozen, as per DIRECTIVE.md)

**Escalation ladder — cheapest first, stop at first answer.**
Hard cap 15 TOTAL ops (CLI + shell reads combined):

0. `--init` once (idempotent). Never `--wipe`, never `--diff`.
1. MAP: `--map-tokens 2048`. Visible answer → STOP.
2. DETECT: `--detect "<query>" --format json --max-results 5`. 1–2 wordings max.
3. SYMBOLS: `--symbols "<query>" --format json` for shapes.
4. READ: hit function body ONLY, max ~120 lines, ONE window per file unless grep justifies second.
5. T1: `--tier 1 --context-lines 3`. Visible answer → STOP.
6. FULL FILE: last resort only.

**v1.6 tool feature:** `--smart-map QUERY` = probe + ONE exact detect (capped at 5) + conditional MAP. If exact hit → outputs detect results + 1 related symbol from same dir, SKIPS MAP. Else falls through to MAP.

---

## HARNESS — THIS RUN ONLY

- Repo: `D:\Projects\Tricorder-Testing-Repos\rails`
- CLI: `python C:\Users\macdo\AppData\Local\Temp\opencode\tricorder-fix-parallel-qualify\tricorder.py`
- Warm DB (4,470 files, ranks live): `--init` SKIPPED, NO `--db-path`, NO rescan.
- **MUST use `--smart-map "has_many"` as FIRST call.** Then targeted reads (≤120 lines, ONE window/file).
- NO `--init`, NO `--db-path`, NO rescan.
- **15 TOTAL ops cap (CLI + reads). Count them.**
- Stay in repo. No network, no installs.
- Final answer: citations with file + line + symbol.

## RETURN

1. Answer with citations (file + line + symbol).
2. Exact commands in order (CLI + reads).
3. Per command: hits + usefulness.