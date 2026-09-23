# Leg A-G1 attempt 1 — TRANSCRIPT (agent report, verbatim)

Model: default (me). 5/20 calls used. Prompt:
`v13/leg-A-G1-attempt1/prompt.md` (full ladder incl. MAP rung 1 as written;
canonical DB, no `--db-path`).

## Answer (as returned)

- Mark phase: `src/runtime/mgc.go` (orchestration: `gcMark`, `gcMarkDone`,
  `gcMarkTermination`) + `src/runtime/mgcmark.go` (helpers:
  `gcMarkRootCheck`, `gcMarkTinyAllocs`, ...).
  - `mgc.go:1972` `func gcMark(startTime int64)` — mark entry.
  - `mgc.go:997` `func gcMarkDone()` — background-mark completion.
  - `mgc.go:1360` `func gcMarkTermination(stw worldStop)` — STW termination.
- Background workers run `gcBgMarkWorker`:
  - `mgc.go:1766` `func gcBgMarkWorker(ready chan struct{})` — infinite
    loop: `gopark(...waitReasonGCWorkerIdle...)`,
    `gcDrainMarkWorkerDedicated/Fractional/Idle`, `gcMarkDone()` on
    `gcEndWork()==true`. Body verified lines 1766–1931.

## Commands (in order, `--root <go> --format json` throughout)

1. `--map-tokens 2048` — 0 hits (120s timeout, no output). NOT useful as
   answer; useful as finding (MAP times out on ~13k-file repo); moved on.
2. `--symbols "gcBgMarkWorker"` — 3 hits (func 1766–1931 + 2 node types).
   USEFUL, exact answer for the worker.
3. python read mgc.go 1766–1931 (full body). USEFUL, confirms loop.
4. `--symbols "gcMark"` — 10 hits (`gcMark:1972`, `gcMarkDone:997`,
   `gcMarkTermination:1360`, `gcmarknewobject`, `gcMarkRootCheck`,
   `gcMarkTinyAllocs`, ...). USEFUL, locates mark-phase files.
5. python read mgc.go 1972–1999 (`gcMark` header). USEFUL, confirms entry.

## Payload artifacts (re-run post-leg against canonical DB)

- `step_symbols_worker.txt` (cmd 2), `step_symbols_gcmark.txt` (cmd 4) —
  raw CLI stdout (default max-results 10, as the agent ran them).
- `step_read_worker.txt` (cmd 3 range), `step_read_gcmark.txt` (cmd 5) —
  file slices as read. Cmd 1 delivered nothing: no artifact, counted 0.
  Metered with `v13/meter_leg.py`.
