# Leg A-G3 attempt 1 — TRANSCRIPT (agent report, verbatim)

Model: default (me). 6/20 calls used. Prompt:
`v13/leg-A-G3-attempt1/prompt.md` (full ladder incl. MAP rung 1 as written;
canonical DB, no `--db-path`).

## Answer (as returned)

Channel send/receive in `src/runtime/chan.go`:

- Send: `func chansend(c *hchan, ep unsafe.Pointer, block bool,
  callerpc uintptr) bool` — `chan.go:168` (ends 302). Header verified
  line 168. Wrapper `func chansend1(c *hchan, elem unsafe.Pointer)` at
  `chan.go:160–162` calls `chansend(c, elem, true, ...)`.
- Receive: `func chanrecv(c *hchan, ep unsafe.Pointer, block bool)
  (selected, received bool)` — `chan.go:516` (ends 678). Header verified
  line 516. Wrappers `func chanrecv1` at `chan.go:500–502` and `func
  chanrecv2` at `chan.go:505–508` both call `chanrecv`.

## Commands (in order, `--root <go> --format json` throughout)

1. `--map-tokens 2048` — 0 hits (120s timeout). Not useful as answer;
   timeout itself a finding; moved on.
2. `--help` — syntax discovery (confirmed `--symbols/--detect/--tier`
   shapes). Useful to the agent, pure overhead to the score.
3. `--symbols "chansend"` — 10 hits (`runtime/chan.go:168 chansend`,
   `:160 chansend1`, `reflect/value.go:3680 chansend`, ...). Exact
   symbol guess first per v1.3. USEFUL.
4. `--symbols "chanrecv"` — 10 hits (`runtime/chan.go:516 chanrecv`,
   `:500 chanrecv1`, `:505 chanrecv2`). USEFUL.
5. python read chan.go 160–183 — verified `chansend1` + `chansend`
   docstring/body start. USEFUL.
6. python read chan.go 500–531 — verified `chanrecv1/chanrecv2` +
   `chanrecv` docstring/body start. USEFUL.

## Payload artifacts (re-run post-leg against canonical DB)

- `step_help.txt` (cmd 2), `step_symbols_chansend.txt` (cmd 3),
  `step_symbols_chanrecv.txt` (cmd 4) — raw CLI stdout.
- `step_read_send.txt` (cmd 5 range), `step_read_recv.txt` (cmd 6) —
  file slices as read. Cmd 1 delivered nothing: no artifact, counted 0.
  Metered with `v13/meter_leg.py`.
