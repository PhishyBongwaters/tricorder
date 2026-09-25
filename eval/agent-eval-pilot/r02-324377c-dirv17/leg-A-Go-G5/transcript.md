| # | Command | Result Summary |
|---|---------|---------------|
| 1 | `tricorder.py --init --root go --db-path go.db` | DB initialized at D:\Projects\tricorder\.tricorder\db\go.db |
| 2 | `tricorder.py --probe-digest --root go --db-path go.db` | 10806 code files (10618 go, 115 c, 30 cpp), ~2121K lines |
| 3 | `tricorder.py --smart-map "SSA form build function" --format json` | Low coverage (0.1%), returned generic builtin symbols — not relevant |
| 4 | `tricorder.py --detect "ssa" --format json --max-results 5` | Found ssaGen* functions in amd64/arm64 codegen (ssagen), not SSA building |
| 5 | `tricorder.py --detect "buildssa" --format json --max-results 5` | Found `buildssa` at ssagen/ssa.go:302 — the SSA builder function |
| 6 | `tricorder.py --detect "ssa.NewFunc" --format json --max-results 5` | Found `ssa.NewFunc` at ssa/func.go:139 — creates SSA Func from config |
| 7 | `tricorder.py --detect "ssa.Compile" --format json --max-results 5` | Matched package name ssacompile, not the function |
| 8 | `tricorder.py --detect "ssa func build" --format json --max-results 5` | Found BuildFuncDebug (debug info), not the main builder |
| 9 | `tricorder.py --symbols "buildssa" --format json --max-results 5` | Confirmed `buildssa` at ssagen/ssa.go:302, signature: `buildssa(compiler ssa.Compiler, fn *ir.Func, worker int, isPgoHot bool)` |
| 10 | Read ssagen/ssa.go lines 302-421 | Full buildssa body: creates ssafn frontend, calls ssaConfig.NewFunc(&fe, cache), walks fn.Body to build SSA |
| 11 | `tricorder.py --detect "Compile(ssacompiler" --format json --max-results 5` | Found ssagen.Compile at pgen.go:305 which calls buildssa |
| 12 | `tricorder.py --detect "Frontend" --format json --max-results 5` | Found ssa.Frontend interface at ssa/config.go:65 |
| 13 | `tricorder.py --detect "ssaFrontend struct" --format json --max-results 5` | Found TestFrontend (test), ssagen.Compile calls buildssa |
| 14 | `tricorder.py --symbols "Compile" --format json --max-results 10` | Found ssagen.Compile at pgen.go:305, ssacompile.Compile at compile.go:38 |
| 15 | `tricorder.py --detect "func compile(" --format json --max-results 10` | Various compile functions, not the main entry |
| 16 | `tricorder.py --detect "ssagen Compile" --format json --max-results 5` | Matched package names |
| 17 | `tricorder.py --detect "func Compile(fn *ir" --format json --max-results 5` | Found AbiForBodylessFuncStackMap, AnalyzeFunc, BuildFuncDebug |
| 18 | `tricorder.py --detect "func Compile(ssa" --format json --max-results 5` | Found buildssa at ssa.go:302, ssagen.Compile at pgen.go:305 |
| 19 | `tricorder.py --detect "func Compile" --format json --max-results 10 --root gc` | Found compileFunctions at gc/compile.go:136 |
| 20 | Read gc/compile.go lines 136-201 | compileFunctions calls `ssagen.Compile(ssacompile.Compiler{}, fn, workerId, profile)` at line 174 |
| 21 | Read pgen.go lines 300-349 | ssagen.Compile calls buildssa at line 306, then genssa |
| 22 | `tricorder.py --detect "ssafn struct" --format json --max-results 5` | Found ssafn at ssagen/ssa.go:7993 — the SSA frontend implementation |
| 23 | Read ssagen/ssa.go 302-421 | Saved to step_10_buildssa_body.txt |
| 24 | Read gc/compile.go 136-201 | Saved to step_19_compileFunctions.txt |
| 25 | Read ssagen/pgen.go 300-349 | Saved to step_20_pgenCompile.txt |
