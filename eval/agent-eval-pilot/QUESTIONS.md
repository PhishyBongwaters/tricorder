# Validated NL questions (agent-eval question book)

One canonical question per repo for headline A/B tallies (round r02+).
The agent receives the question text ONLY — no keywords, no ground
truth; it discovers search terms itself. Grading is ground-truth
citation (file + line + symbol), audited against transcripts.

## Canonical six

### VW-Q1 — Vaultwarden, TOTP verification
- Q: "Where is TOTP two-factor code verification implemented?"
- GT: `validate_totp_code`, `src/api/core/two_factor/authenticator.rs:115`
  (wrapper `:101`, caller `:57/:83`).
- Source: v13 leg-A-VW-Q1-attempt1 (PASS).

### Go-G5 — Go compiler, SSA build
- Q: "Where does the Go compiler build SSA form for a function, and which
  function is the entry point?"
- GT: `src/cmd/compile/internal/ssagen/ssa.go:302 func buildssa`
  (caller `pgen.go:305 Compile` confirms the chain).
- Source: v13 leg-A-G5-attempt2 (PASS). Richest history: the 58k-token
  junk query that motivated exact-first + rescue gate.

### Rails-Q1 — ActiveRecord has_many
- Q: "How does ActiveRecord implement the `has_many` association and what
  methods does it generate?"
- GT: `has_many` at `activerecord/lib/active_record/associations.rb:1426`
  → `Builder::HasMany.build()` → `HasManyReflection`; generated
  `#{name}`, `#{name}=`, `#{name}_ids`, `#{name}_ids=`.
- Source: v13 leg-A-Rails-Q1-attempt2 (PASS, smart-map compliant).

### Elixir-Q1 — GenServer behaviour
- Q: "How does Elixir implement the GenServer behaviour - what callbacks
  must a server module implement, and how do client calls reach the
  server process?"
- GT: `lib/elixir/lib/gen_server.ex` (verified 2026-09-25, local tree):
  `@callback handle_call` :647, `def start_link` :1077, `def call`
  :1172. Accept any subset proving file + callbacks + client path.
- Source: v13 leg-A-Elixir-Q1-attempt1 (PASS, rung-4 overbreadth noted).

### Vue-Q1 — reactivity system
- Q: "How does Vue implement its reactivity system - where are data
  properties intercepted, and how are dependent watchers notified of
  changes?"
- GT: `defineReactive`, `src/core/observer/index.ts:128`
  (getter/setter interception); `Dep`, `src/core/observer/dep.ts:31`
  (`dep.notify()` fan-out).
- Source: v13 leg-A-Vue-Q1-attempt1 (PASS, minor chaining exceedance).

### Swift-Q1 — expression parser (authored 2026-09-25, NEW)
- Q: "Where is the Swift expression parser implemented?"
- GT (verified by direct read 2026-09-25, local swift tree):
  `Parser::parseExpr`, `include/swift/Parse/Parser.h:1778` (entry,
  delegates to `parseExprImpl`); implementation
  `Parser::parseExprImpl`, `lib/Parse/ParseExpr.cpp:48`.
- Accept either cite (entry or implementation) with exact line+symbol.
- Note: supersedes the scripted Q4 (`parseExpr` → `lib/Parse/ParseExpr.cpp`,
  file-level only) with symbol-level ground truth.

## Depth panel (validated, NOT in headline rounds)

Kept for variance studies; zero authoring cost, already graded PASS:
- VW-Q2 "How does the admin panel authenticate requests?"
  (`AdminToken` guard `src/api/admin.rs:857`).
- VW-Q3 "Where are organization collection access permissions checked?"
  (`Collection::can_access_collection`, `collection.rs:155`).
- VW-Q4 "How are live notifications sent when a cipher changes?"
  (`send_cipher_update`, `notifications.rs:430`).
- Go-G1 "Where is the Go garbage collector's mark phase implemented, and
  what function do the background mark workers run?"
  (`mgc.go:1766 gcBgMarkWorker`, `mgcmark.go:1253 gcDrain`).
- Go-G3 "Where are channel send and receive operations implemented in
  the Go runtime?" (`chan.go`, `chansend` + `chanrecv`).

## Scripted runs (NOT agent legs — labeled honestly)

- `eval/comparison-runs/2026-09-21/` (Vaultwarden/Go, oracle keywords,
  no live agent — perfect-world upper bound, NOT end-to-end).
- `eval/comparison-runs/2026-09-22/` (Swift Q1–Q5, same method).
- A past agent ran scripted subprocesses; scores stand as retrieval
  metrics but must never be quoted as agent-eval numbers.
