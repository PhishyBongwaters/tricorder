# Leg A-Go-G5 — GRADE (Qwen model) — TOKENS VOID, CITATION STANDS

## Verdict: PASS on citation, compliance FAIL (over cap), TOKENS VOID

Operator ruling 2026-09-25: only 6 of ~20 payloads were saved despite
an explicit save-everything instruction, so no valid token total exists
for this leg. The 699 figure below is a metered floor over surviving
artifacts, NOT a total, and must never enter a tally. Citation and
compliance findings stand as behavioral data. Re-run as attempt2 with
enforced saving; this attempt's token cell stays VOID permanently.

Ground truth (`src/cmd/compile/internal/ssagen/ssa.go:302 func
buildssa`) cited exact with signature; chain confirmed (`pgen.go:305
Compile` calls `buildssa` :306; driver `gc/compile.go:136
compileFunctions`). Answer correct and complete.

## Tokens (metered floor — see gap note)

6 artifacts saved: 699 tokens total (init 30, probe 23, 3 reads
237+161+180, 1 detect 68). ~14 detect/symbols payloads UNSAVED despite
explicit prompt instruction — true cost unmetered and much higher.

## Compliance: FAIL

- **Over cap: 25 calls > 20.** Answer found at call 5 (`buildssa`
  ssa.go:302), confirmed at call 9 (symbols + signature) — then 13 more
  tricorder calls before the first read.
- **Wording violations**: ~14 detect wordings vs 1–2 max; call 13
  repeats call 12 verbatim (`ssaFrontend struct`); calls 14/15/19 use
  `--max-results 10` against the cap-5 rule.
- Payload-saving instruction disobeyed (6 of ~20 saved).

## Product diagnosis (no bug — no stop-the-line)

Operator investigated "lost agent / fucked coverage" before grading:
- `file_ranks` healthy (n=10,766, sum=1.0, skewed; top =
  `builtin.go`, `encoding/gob`, `go/ast` — heavily-referenced core).
- 2048-tok MAP on 278k defs honestly renders ~4 files (0.1% coverage
  warning intact). Thin, not broken — inherent to the budget at this scale.
- Smart-map behaved per v1.7 (over 5000 files → straight to MAP; MAP
  valueless-but-honest; agent correctly descended to detect).
- Wandering is model variance: Qwen over-verified instead of stopping.
  v13's tight G5 (7 calls) ran a different model with a timed-out MAP
  forcing detect-first. Lesson, not defect.

## Finding for v1.8 (tuning evidence, NOT a mid-round change)

On Go-scale repos the 2048 MAP rung delivers ~4 files — honest but
near-valueless; the ladder effectively starts at rung 2 there. Whether
rung 1 should be skipped (or the budget scaled) on 10k+ file repos is a
directive question for after the round.
