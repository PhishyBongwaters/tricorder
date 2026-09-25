# Answer: Where the Go Compiler Builds SSA Form and the Entry Point

## Question: "Where does the Go compiler build SSA form for a function, and which function is the entry point?"

## Answer

### Where SSA form is built

SSA form for a function is built in the function **`buildssa`** at:

- **File:** `src/cmd/compile/internal/ssagen/ssa.go`
- **Line:** 302
- **Symbol:** `func buildssa(compiler ssa.Compiler, fn *ir.Func, worker int, isPgoHot bool) (*ssa.Func, ssa.HTMLWriter)`

The `buildssa` function builds SSA form by:

1. **Creating a frontend** (`ssafn` struct, defined at `src/cmd/compile/internal/ssagen/ssa.go:7993`) that implements the `ssa.Frontend` interface (`src/cmd/compile/internal/ssa/config.go:65`). This frontend provides the IR-to-SSA translation logic.

2. **Allocating the SSA function** via `ssaConfig.NewFunc(&fe, cache)` at line 365, which calls `ssa.Config.NewFunc` (`src/cmd/compile/internal/ssa/func.go:139`) to create the `*ssa.Func` structure.

3. **Walking the IR function body** (`fn.Body`) and converting each IR node into SSA values and blocks. The SSA function's entry block is allocated at line 382 (`s.f.Entry = s.f.NewBlock(block.BlockPlain)`).

### Entry point function

The entry point that triggers SSA building for a single function is:

- **File:** `src/cmd/compile/internal/ssagen/pgen.go`
- **Line:** 305
- **Symbol:** `func Compile(ssacompiler ssa.Compiler, fn *ir.Func, worker int, profile *pgoir.Profile)`

This function (comment: "Compile builds an SSA backend function, uses it to generate a plist, and flushes that plist to machine code") calls `buildssa` at line 306, then generates machine code via `genssa`.

### Top-level caller

The top-level function that drives compilation of all functions in a package is:

- **File:** `src/cmd/compile/internal/gc/compile.go`
- **Line:** 136
- **Symbol:** `func compileFunctions(profile *pgoir.Profile)`

It spawns worker goroutines that each call `ssagen.Compile(ssacompile.Compiler{}, fn, workerId, profile)` at line 174 for each function in the compile queue.

### Call chain summary

```
compileFunctions (gc/compile.go:136)
  └── ssagen.Compile (ssagen/pgen.go:305)
        └── buildssa (ssagen/ssa.go:302)
              ├── ssafn frontend created (ssagen/ssa.go:7993)
              └── ssaConfig.NewFunc(&fe, cache) (ssa/func.go:139)
                    └── SSA form built for the function
```
