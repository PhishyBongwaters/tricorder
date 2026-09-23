# Leg B-G1 attempt 1 — TRANSCRIPT (agent report, verbatim)

Model: default (me — same model both sides). 10/20 calls used. Prompt:
`v13/leg-B-G1-attempt1/prompt.md` (baseline tools only).

## Answer (as returned)

- Core marking: `src/runtime/mgcmark.go` — `gcDrain:1253` (drain loop:
  roots via `markroot` + heap via `scanObject`/`scanSpan`), wrappers
  `gcDrainMarkWorkerIdle:1181` / `Dedicated:1187` / `Fractional:1197`,
  `gcPrepareMarkRoots:109`, `markroot:221`, `gcNextMarkRoot:1205`.
- Orchestration: `src/runtime/mgc.go` — `gcBgMarkStartWorkers:1688`,
  `gcBgMarkPrepare:1731`, `gcMarkDone:997`, `gcMarkTermination:1360`,
  `gcMark:1972`.
- Workers run `gcBgMarkWorker(ready chan struct{})` at `mgc.go:1766`
  (park → drain variants → `gcMarkDone()` loop), spawned as `go
  gcBgMarkWorker(ready)` at `mgc.go:1711` inside `gcBgMarkStartWorkers`.

## Commands (in order, relative to the Go repo)

1. read `src/runtime` dir (~792 entries incl `mgc.go, mgcmark.go`)
2. bare `grep -rn gcBgMarkWorker` → error (PowerShell, no grep);
   delivered nothing
3. `Select-String src\runtime\*.go gcBgMarkWorker` → hits incl `func
   gcBgMarkWorker` at 1766
4. sizes + line counts (`mgc.go` 79497B/2085 lines, `mgcmark.go`
   56759B/1642 lines)
5. read mgc.go 1660–1899 (StartWorkers/Prepare/Worker + dispatch)
6. read mgc.go 1900–1959 + mgcmark.go 1–120 (worker tail, file purpose)
7. grep `^func gc.*Mark|^func gcDrain|^func markroot` in mgcmark.go
   (PrepareMarkRoots:109, markroot:221, drain wrappers, gcDrain:1253, ...)
8. grep `^func gcMark|^func gcDrain|^func gcBgMark` in mgc.go
   (orchestration map)
9. read mgc.go 1972–2085 + mgcmark.go 1253–1422 (`gcMark` + `gcDrain`
   bodies)
10. read mgc.go 997–1101 + mgcmark.go 1181–1255 (`gcMarkDone` + wrappers)

## Payload artifacts

`step*.txt` reproduced post-leg from disk by `meter.py`, plus
`meter.json`. Cmd 2 delivered nothing: no artifact, counted 0. No
tricorder command anywhere — baseline-only audit clean.
