# Comparison re-run — 2026-09-22 (Swift, both arms fresh)

Re-measures the Swift 5-question comparison on branch tip after the Q4
crowding fix (`090456e`, detect results interleave per file before the
result cap). **Both arms re-run together** — baseline numbers are not
reused from 9/21 (see why below). Method identical to 9/21: prescan each
variant into its own DB (scan paths `lib`+`include`, `--map-tokens` 500,
cost sunk), then per question 2× `detect(keyword, pre_index=keyword)`,
tokens via tiktoken `cl100k_base` through tip `utils.count_tokens`,
same frozen questions/keywords/ground truth and grading as 9/21.
Scripted rung policy throughout — no live agent or model; "pass" means
the ground-truth path was cited in the returned payloads.

- Branch measured: `fix/parallel-qualify` @ `202607d`
- Baseline measured: `dev/db-map` @ `438fd0b` (frozen, same commit as 9/21)
- Corpus: swiftlang/swift PR #92459 head @ `c5cb7c3` — the 9/21 tree
  (`20441c6`) was rebased out of the PR and is unfetchable; this is the
  closest obtainable tree (21 files differ out of ~32.8k; all 5
  ground-truth files verified present). Scope `lib`+`include`: 2,421
  files, 726,547 tags indexed per variant.
- Machine: WSL2 Ubuntu, 8 CPUs, ripgrep 14.1.0 (pre-index fast path).
- Prescan (sunk, uncharged): baseline 240.3s, branch 118.8s. First rungs
  ~300s (cold cross-file index build), later rungs seconds (disk-cached).

## Results

| Question | Baseline | Branch | Delta |
|---|---|---|---|
| Q1 Function-call type checking | 13,469 | 1,121 | −91.7% |
| Q2 SIL inliner cost model | 2,111 | 1,092 | −48.3% |
| Q3 String interpolation | 7,992 | 2,229 | −72.1% |
| Q4 Expression parser | 6,813 | 1,024 | −85.0% |
| Q5 Qualified name lookup | 8,500 | 2,142 | −74.8% |
| **Total (5/5 both)** | **38,885** | **7,608** | **−80.4%** |

(Q2 measured 1,411 branch on 9/21 on the older tip; every number in the
table above was measured fresh in this run.)

**Q4 flips PASS:** branch evidence cites `lib/Parse/ParseExpr.cpp` — the
interleave fix works end-to-end. Swift is now 5/5 on both arms.

## Why both arms (note on baseline drift)

Baseline totals differ from 9/21 (69,875 → 38,885) on frozen baseline
code: detect result order follows filesystem traversal order, which
differs between machines, so top-10 payloads shift. Same-tree,
same-machine pairing is what makes an A/B valid — hence both arms fresh
here. The 9/21 Swift baseline is superseded by this run's baseline; the
9/21 Vaultwarden and Go runs stand (their A/Bs were internally paired).

## Combined headline (per-repo paired sums)

- Vaultwarden 9/21: 26,818 → 8,987 (−66.5%), 4/4 both
- Go 9/21: 19,688 → 8,751 (−55.5%), 3/3 both
- Swift 9/22 (this run): 38,885 → 7,608 (−80.4%), 5/5 both
- **Combined (12/12 both): baseline 85,391 → branch 25,346 (−70.3%)**

## Layout

- `artifacts/<qid>/<variant>/` — `steps.json`, `evidence.txt`,
  `grade.json`, `step_detect1/2.txt` per question and arm
- `results.csv` — question,variant,tokens,pass,gt_existing
- `prescan.json`, `prescan_<variant>.log` — sunk prescan records

Excluded (not portable): the Swift checkout, built index DBs, venv.
Reproduce: shallow-ish checkout of the recorded tree, `pip install -e .`,
prescan with `--map-tokens 500` over `lib include`, then 2× detect per
question keywords above.
