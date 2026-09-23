# Leg A-G5 attempt 2 — TRANSCRIPT (agent report, verbatim)

Model: default (me). 7/20 calls used. Prompt:
`v13/leg-A-G5-attempt2/prompt.md` (approved pre-launch).

## Answer (as returned)

Go compiler builds SSA form for a function in
`src/cmd/compile/internal/ssagen/ssa.go:302`, entry point `buildssa` —
`func buildssa(compiler ssa.Compiler, fn *ir.Func, worker int, isPgoHot
bool) (*ssa.Func, ssa.HTMLWriter)` with comment `// buildssa builds an
SSA function for fn.` Caller/entry wrapper:
`src/cmd/compile/internal/ssagen/pgen.go:305` `func Compile(ssacompiler
ssa.Compiler, fn *ir.Func, worker int, profile *pgoir.Profile)` calls
`f, htmlWriter := buildssa(...)` then generates plist/machine code.

## Commands (in order; base flags `--root <go> --db-path <warmdb>
--format json` on every CLI call)

1. `--map-tokens 2048` — hits: 0 (timeout after 120s) — useful: no.
2. `--symbols "buildSSA"` — hits: 1 (`buildssa` in
   `src/cmd/compile/internal/ssagen/ssa.go:302-632`) — useful: yes,
   direct answer.
3. `powershell -NoProfile -Command "Get-Content ..."` — exit 1, bad
   `-Command` wrapping — useful: no (harness error, recovered next call).
4. `Get-Content '.../ssagen/ssa.go' | Select-Object -First 40 -Skip 295`
   — lines 296–335 showing `// buildssa builds an SSA function for fn.`
   + `func buildssa(...)` — useful: yes, verified.
5. `--symbols "compileSSA"` — hits: 10 fuzzy (`*_ssa` test funcs in
   `fp_test.go`/`arithBoundary_test.go`) — useful: no, junk/wrong-area.
6. `--detect "buildssa builds SSA function" --max-results 5` — hits: 5
   (top hit `pgen.go:305 Compile` calling `buildssa`, rest junk) —
   useful: yes, confirmed caller.
7. `Get-Content '.../ssagen/pgen.go' | Select-Object -First 15 -Skip 300`
   — lines 301–315 showing `func Compile(...)` + `buildssa(...)` call —
   useful: yes, verified.

## Payload artifacts (re-run post-leg against warm DB, deterministic code)

- `step_symbols_buildSSA.txt` (cmd 2), `step_symbols_compileSSA.txt`
  (cmd 5), `step_detect_nl5.txt` (cmd 6) — raw CLI stdout.
- `step_read_ssa.txt` (cmd 4 range), `step_read_pgen.txt` (cmd 7 range)
  — file slices as read.
- Cmds 1 (timeout) and 3 (harness error) delivered nothing: no artifact,
  counted 0. Metered with `v13/meter_leg.py`.
