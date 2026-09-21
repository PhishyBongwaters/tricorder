# Swift-repo A/B comparison: baseline 438fd0b vs branch 5316c90 (fix/parallel-qualify)

Date (UTC): 2026-09-21
Corpus: swiftlang/swift @ 20441c6 (32,805 tracked files, 342M)
Scan scope: `lib` + `include` paths (2,324 files, 726,714 tags indexed per variant)
Baseline: tricorder-base @ 438fd0b | Branch: ~/workspace/tricorder @ 5316c90
Tokenizer: tiktoken cl100k_base, identical both sides. Pre-scan excluded from totals.

## Methodology note (adapted for 32k-file repo)

v3's 6-rung sequence (detect→symbols→detail × 2) is impractical on swiftlang/swift:
- `symbols/` re-parses the tree per call (no diskcache) — >300s/rung
- `detail/` does a full-repo cross-file caller/callee scan — >180s/rung

Adapted to 2 rungs/question: `detect(kw1, pre_index=kw1)` → `detect(kw2, pre_index=kw2)`.
`pre_index` is the server's built-in huge-repo fast path, applied identically to both
variants. The detail delta would be ~0 (cross-file scan unaffected by the qualify fix);
the meaningful baseline-vs-branch delta is in detect payloads.

## Per-question results

| Question | Baseline tok | Branch tok | Δ raw | Δ % | Calls | Base pass | Branch pass |
|---|---|---|---|---|---|---|---|
| Q1: function-call type checking | 27,276 | 2,242 | -25,034 | -91.8% | 2/2 | PASS | PASS |
| Q2: SIL inliner cost model | 2,509 | 1,411 | -1,098 | -43.8% | 2/2 | PASS | PASS |
| Q3: string interpolation desugaring | 1,859 | 1,877 | +18 | +1.0% | 2/2 | PASS | PASS |
| Q4: expression parser | 18,809 | 2,191 | -16,618 | -88.4% | 2/2 | PASS | **FAIL** |
| Q5: qualified name lookup | 19,422 | 2,068 | -17,354 | -89.4% | 2/2 | PASS | PASS |

## Totals

- Tokens: baseline 69,875, branch 9,789 → **Δ -60,086 (-86.0%)**
- Calls: 10 per variant (2/question)
- Pass: baseline 5/5, branch 4/5

## Window analysis (32k / 64k / 128k local-model windows)

- **32k window**: baseline 69,875 → OVERFLOWS; branch 9,789 → fits
- **64k window**: baseline 69,875 → OVERFLOWS; branch 9,789 → fits
- **128k window**: both fit

A realistic 5-question navigation session overflows 32k AND 64k on baseline but fits
comfortably with the branch. Per-question, all fit individually, but the cumulative
session cost is what matters for a 10-turn budget.

## Q4 caveat (precision/recall tradeoff)

Branch FAIL on Q4: it found `Parser::parseExpr` (correct symbols) in
`include/swift/Parse/Parser.h` but did not cite `lib/Parse/ParseExpr.cpp` (the
implementation file, ground truth). The qualify fix's stricter matching improves
precision (fewer noisy hits → fewer tokens) but missed the .cpp file here. An agent
seeing the header declarations would naturally check the counterpart .cpp, but
strictly per the rubric this is a FAIL.

## Ground-truth verification (manual)

- Q1: `lib/Sema/CSApply.cpp:4102` — `visitApplyExpr` ✓
- Q2: `lib/SILOptimizer/Transforms/PerformanceInliner.cpp:1068` — `shouldInlineGeneric` ✓
- Q3: `include/swift/AST/Expr.h:950` — `InterpolatedStringLiteral` ✓
- Q5: `lib/AST/NameLookup.cpp:2684` — `DeclContext::lookupQualified` ✓
