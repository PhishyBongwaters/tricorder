# Leg A-Rails-Q1 attempt 1 — GRADE (Qwen model)

## Verdict: PASS — **Ladder compliant, but symbol cap violation**

Ground truth (`has_many` at `associations.rb:1426`, `Builder::HasMany`,
`HasManyAssociation`) cited with lines and verified by reads. 7/15 calls.

## Tokens

| Step | Tokens | Note |
|---|---|---|
| MAP 2048 | 2,075 | generic Rails scaffolding |
| symbols "has_many" | 23,617 as-run → **1,430 post-fix** | monster name fixed (see Findings) |
| symbols "HasMany" | 1,357 | confirmed builder/association |
| detect "has_many association" | 1,204 | right area |
| reads (4 ranges) | 1,948 | verified |
| **Total** | **30,201 as-run / 8,014 post-fix replay** | |

## Compliance

- Ladder: MAP → SYMBOLS → SYMBOLS → DETECT → READ ×4
- **Violation**: v1.3 directive says "NL queries run with `--max-results 5`. Widen to 10 only when the narrow pass returns nothing usable." The same principle applies to symbol queries — first pass should be capped.
- Agent did not cap `symbols "has_many"` → 500+ matches returned
- Exact-first on detects: obeyed; zero NL; zero junk
- Stopped at first rung that answered (READ rung)

## Model Tracking

| Leg | Model | Provider |
|---|---|---|
| A-Rails-Q1 | **Qwen** | **llamacpp** |
| A-VW-Q3/Q4, A-G1-Qwen | Qwen | llamacpp |
| All other v1.3 legs | Nemotron | opencode |

## Findings

1. **Monster-name extractor bug — fixed at source.** `symbols "has_many"`
   returned one 70,512-char "name" (entire Ruby module + RDoc, 23,617
   tok). Root cause: greedy document-order name pairing let an outer
   nested scope steal the inner scope's name node; the inner definition
   fell through to unbounded `parent.text`. Fix (`parser.py`): pair
   innermost-first (stable span sort) + bound the last resort to first
   line ≤200 chars. Red-first `tests/test_symbol_name_span.py`.
   Post-fix identical query: 1,430 tok (16.5×). Initial "cap violation"
   read was wrong — limit held (10 records); one record was poisoned.
2. **MAP rung still noise** — at 4.5k files MAP works mechanically (2,075 tok fitted) but returns generic scaffolding; exact-first symbols bypass it.
3. **Qwen still ladder-compliant** — stopped at first answer (READ rung), no NL, no junk.
4. **As-run 30,201 vs post-fix replay 8,014** — the monster record was
   78% of the leg.
5. **Records hygiene:** `.rb` payload artifacts broke
   `test_empty_result` (scans the worktree; Ruby modules type as
   `import`). Artifacts renamed `.rb.txt`; parseable extensions must
   never be committed as records.