# Leg A-Rails-Q1 attempt 1 — GRADE (Qwen model)

## Verdict: PASS — **Ladder compliant, but symbol cap violation**

Ground truth (`has_many` at `associations.rb:1426`, `Builder::HasMany`,
`HasManyAssociation`) cited with lines and verified by reads. 7/15 calls.

## Tokens

| Step | Tokens | Note |
|---|---|---|
| MAP 2048 | 2,075 | generic Rails scaffolding |
| symbols "has_many" | 23,617 | **500+ matches; cap violation (v1.3 §)** |
| symbols "HasMany" | 1,357 | confirmed builder/association |
| detect "has_many association" | 1,204 | right area |
| reads (4 ranges) | 1,250 | verified |
| **Total** | **28,253** | **5× inflated by uncapped symbols** |

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

1. **Symbol query blowup on large codebases**: `symbols "has_many"` matched 500+ definitions across Rails (every model using it, plus builder classes, test files, etc.). v1.3 cap should apply to symbols too.
2. **MAP rung still noise** — at 4.5k files MAP works mechanically (2,075 tok fitted) but returns generic scaffolding; exact-first symbols bypass it.
3. **Qwen still ladder-compliant** — stopped at first answer (READ rung), no NL, no junk.
4. **As-run tokens 28k vs expected ~5k** — 5× inflation from uncapped symbol query.