# Leg B-G5 attempt 1 — TRANSCRIPT (agent report, verbatim)

Model: default (me — same model both sides). 16/20 calls used. Prompt:
`v13/leg-B-G5-attempt1/prompt.md` (baseline tools only: reads, listings,
grep via shell; no tricorder; stay in repo).

## Answer (as returned)

- SSA-for-a-function is built in
  `src/cmd/compile/internal/ssagen/ssa.go:302` —
  `func buildssa(compiler ssa.Compiler, fn *ir.Func, worker int,
  isPgoHot bool) (*ssa.Func, ssa.HTMLWriter)` with comment `// buildssa
  builds an SSA function for fn.`
  - `ssa.go:365` `s.f = ssaConfig.NewFunc(&fe, cache)`,
    `ssa.go:382` entry block, `ssa.go:404` `OpInitMem` seed.
  - Lowering: `ssa.go:583` `s.stmtList(fn.Body)` (+ `s.exit()` at
    `ssa.go:588`), `s.insertPhis()` at `ssa.go:602`.
  - Backend handoff: `ssa.go:604-605` + `compiler.Compile(s.f,
    htmlWriter)`.
- Entry wrapper: `src/cmd/compile/internal/ssagen/pgen.go:305`
  `func Compile(...)` (`// Compile builds an SSA backend function...`),
  body `pgen.go:306` `f, htmlWriter := buildssa(...)`, `genssa` at
  `pgen.go:316` + `pp.Flush()`.
- Driver: `src/cmd/compile/internal/gc/compile.go:174`
  `ssagen.Compile(...)` inside the compile-queue worker loop.
- Conclusion: `ssagen.Compile` = external entry; `ssagen.buildssa` =
  where SSA form is constructed.

## Commands (in order, relative to the Go repo)

1. read repo root (17 entries)
2. read `src` (~77 entries, found `cmd/`)
3. read `src/cmd` (30 entries, found `compile/`)
4. read `src/cmd/compile` (found `internal/`)
5. read `src/cmd/compile/internal` (52 entries incl `gc/ ssa/ ssagen/`)
6. list `ssagen` + `ssa` file names
7. grep `^func (Build|Compile|Gen|.*SSA)` in `ssagen/*.go` → `pgen.go:305
   func Compile`, `ssa.go:302 func buildssa`, `ssa.go:7006 func genssa`
8. file sizes (ssa.go 274480B, pgen.go 13624B) + grep
   `buildssa|func BuildSSA|genssa` in ssa.go
9. grep `^func |buildssa|Compile\(` in pgen.go → `pgen.go:306`
   `buildssa(...)` call (caller-search half errored on bad `-Include`,
   delivered nothing)
10. grep `func buildssa` in ssa.go + recursive grep
    `ssagen\.Compile|buildssa\(` → 3 hits (`gc/compile.go:174`,
    `pgen.go:306`, `ssa.go:302`)
11. read pgen.go 295–354 (Compile body)
12. read ssa.go 298–362 (buildssa head)
13. read gc/compile.go 160–189 (driver loop)
14. read ssa.go 362–441 (NewFunc/NewBlock/InitMem setup)
15. grep `ssa\.Compile|compiler\.Compile|\.stmt\(|\.stmtList|finishFunc|Free
    IR` in ssa.go → `s.stmtList(fn.Body):583`, `compiler.Compile(s.f):605`
16. read ssa.go 575–624 (stmtList→exit→insertPhis→Compile→AllocFrame)

## Payload artifacts

`step*.txt` reproduced post-leg from disk by `meter.py` (same ranges,
patterns, listings; formats mirror meter_go.py conventions), plus
`meter.json`. No tricorder command appears anywhere in the transcript —
baseline-only audit clean.
