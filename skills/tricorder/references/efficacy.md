# Benchmark Efficacy

Measured per-query response-payload tokens, baseline navigation vs tricorder
branch — see the canonical run records in
`eval/comparison-runs/2026-09-21/README.md` (Vaultwarden, Go) and
`eval/comparison-runs/2026-09-22/README.md` (Swift re-measure)
(tiktoken `cl100k_base`, frozen question corpora with ground-truth
grading). All runs use a scripted rung policy (fixed detect/symbols/detail
sequence, first-hit detail, citation grading) — no live agent or model.
Do not mix these with end-to-end agent-eval numbers
(`bench/bench_agent_eval.py`); do not quote older map-vs-blind percentages,
which ran against previous pipeline versions.

| Repo | Baseline | Branch | Saving | Accuracy |
|------|----------|--------|--------|----------|
| Vaultwarden, 4 questions | 26,818 | 8,987 | −66.5% | 4/4 both |
| Go (`golang/go`), 3 questions | 19,688 | 8,751 | −55.5% | 3/3 both |
| Swift (`swiftlang/swift`), 5 questions, re-measured 2026-09-22 | 38,885 | 7,608 | −80.4% | 5/5 both |
| **Combined, 12 questions (VW+Go 9/21, Swift 9/22)** | **85,391** | **25,346** | **−70.3%** | branch 12/12 |

Caveat (retired 2026-09-22): the 9/21 Swift miss (Q4) was fixed by `090456e`
and re-measured 5/5 in `eval/comparison-runs/2026-09-22/README.md` — the
table above carries the fresh numbers.

**RESULT: measured savings hold with answer parity** — ground truth cited
in 12/12 scripted runs at under a third of the baseline's tokens.

## How to Run Comparisons

```bash
# Scripts + frozen corpora live with the run records:
# eval/comparison-runs/2026-09-21/{scripts,corpora,runs,results-go,results-swift}
```

Old `bench/bench_validity*.py` map-vs-blind suites describe a previous
pipeline version; their numbers are historical (see `docs/benchmarks.md`
banner) — do not present them as current efficacy.
