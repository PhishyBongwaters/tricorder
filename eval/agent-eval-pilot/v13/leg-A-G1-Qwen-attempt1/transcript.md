# Leg A-G1-Qwen attempt 1 — TRANSCRIPT (Qwen model)

Model: `llamacpp/Qwen` (local llama.cpp). 8/20 calls used.
Prompt: `v13/leg-A-G1-Qwen-attempt1/prompt.md` (strict ladder).

## Answer (as returned)

### Where is the Go garbage collector's mark phase implemented?

1. **`src/runtime/mgc.go`**:
   - **`func gcStart(trigger gcTrigger)`** at **line 733** — top-level GC entry point; stops world, starts workers, resets mark state, prepares roots, enables write barrier, enters concurrent mark phase.

2. **`src/runtime/mgcmark.go`**:
   - **`func gcDrain(gcw *gcWork, flags gcDrainFlags)`** at **line 1253** — core mark loop (drains P-local work buffer, scans objects, follows pointers).
   - **`func gcPrepareMarkRoots()`** at **line 109** — prepares root scanning work queue.
   - **`func gcAssistAlloc(gp *g)`** at **line 499** — mutator-assisted marking.

### What function do the background mark workers run?

**`func gcBgMarkWorker(ready chan struct{})`** at **`src/runtime/mgc.go:1766`**:

- Sets up persistent worker node pinned to worker G.
- Infinite loop: `gopark()` until woken by `gcController.findRunnableGCWorker()`.
- Dispatches to drain function based on mode (`pp.gcMarkWorkerMode`):
  - **`gcDrainMarkWorkerDedicated`** (mgcmark.go:1187) — dedicated workers.
  - **`gcDrainMarkWorkerFractional`** (mgcmark.go:1197) — fractional workers.
  - **`gcDrainMarkWorkerIdle`** (mgcmark.go:~1207) — idle workers.
- All call **`gcDrain()`** (line 1253) for actual black/white mark scanning.
- Started by **`gcBgMarkStartWorkers()`** at **mgc.go:1688** (one per P).

## Commands (in order)

| # | Step | Tokens | Hits | Useful? |
|---|---|---|---|---|
| 1 | MAP 2048 | 0 | 0 | ❌ timeout (expected on Go) |
| 2 | detect "gcBgMarkWorker" | 1,065 | 10 | ✅ found mgc.go:1766 |
| 3 | symbols "gcBgMarkWorker" | 374 | 2 | ✅ confirmed mgc.go:1766 |
| 4 | detect "gcDrain" | 1,111 | 10 | ✅ found mgcmark.go:1253 |
| 5 | symbols "gcDrain" | 809 | 7 | ✅ confirmed mgcmark.go:1253 |
| 6 | read mgc.go 1765–1930 | 2,178 | — | ✅ worker body |
| 7 | read mgcmark.go 1252–1419 | 2,060 | — | ✅ gcDrain body |
| 8 | read mgc.go 732–799 | 764 | — | ✅ gcStart entry |

**Total: 8 calls, 8,361 tokens** (MAP rung timeout = 0 tokens)

## Compliance

- MAP rung 1: timed out (expected on Go per prior legs) → correctly continued
- Exact-first: both detect queries were identifier guesses, zero NL
- Ladder: MAP → DETECT → SYMBOLS → DETECT → SYMBOLS → READ ×3
- **Stopped at first rung that answered** (READ rung confirmed full picture)
- Zero junk; zero NL; citation discipline clean