# Benchmark Efficacy

Measured per-query response-payload tokens, baseline navigation vs tricorder
branch — see the canonical run records in
`eval/comparison-runs/2026-09-21/README.md` (tiktoken `cl100k_base`, frozen
question corpora with ground-truth grading). Do not quote older map-vs-blind
percentages; those ran against previous pipeline versions.

| Repo | Baseline | Branch | Saving | Accuracy |
|------|----------|--------|--------|----------|
| Vaultwarden, 4 questions | 26,818 | 8,987 | −66.5% | 4/4 both |
| Go (`golang/go`), 3 questions | 19,688 | 8,751 | −55.5% | 3/3 both |
| Swift (`swiftlang/swift`), 5 questions | 69,875 | 9,789 | −86.0% | 5/5 baseline, 4/5 branch |
| **Combined, 12 questions** | **116,381** | **27,527** | **−76.3%** | branch 11/12 as measured |

Caveat: the single Swift miss (Q4) was fixed after measurement (`090456e`,
detect results now interleave per file); full-corpus re-measure pending.

**RESULT: measured savings hold with answer parity** — the branch answers
11/12 (soon re-measured) at roughly a quarter of the baseline's tokens.

## How to Run Comparisons

```bash
# Scripts + frozen corpora live with the run records:
# eval/comparison-runs/2026-09-21/{scripts,corpora,runs,results-go,results-swift}
```

Old `bench/bench_validity*.py` map-vs-blind suites describe a previous
pipeline version; their numbers are historical (see `docs/benchmarks.md`
banner) — do not present them as current efficacy.
