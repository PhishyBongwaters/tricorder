# Agent-eval v1.3 series — Go-only (2026-09-23)

One repo until satisfied. Sequential legs, one agent at a time.

## Protocol (locked before leg 1)

- **Corpus:** `D:\Projects\Tricorder-Testing-Repos\go` (15,844 files)
- **Tricorder code:** `main` @ `92e14f1` (determinism fix + max_tokens budgets in)
- **Agent vehicle:** subagent, default model (me — same model as the pilot's
  A-legs). Attempt 1 used `llamacpp/Qwen` against instruction; recorded in
  `leg-A-G5-attempt1/ATTEMPT.md`. No model override without per-leg approval.
- **Directive:** v1.3 (exact symbol guess first, NL capped at `--max-results 5`,
  junk-hit retry, ladder map → detect → symbols → read → tier-1 → full file)
- **B-legs:** same question, same 20-call cap, grep/read/glob only, stay in repo
- **Warm DB:** `D:/Projects/Tricorder-Testing-Repos/bench_temp/eval-go-v13.db`
  (prescan sunk, uncharged; DB itself NOT committed — multi-GB, not portable)
- **Prescan cmd:** `python tricorder.py --root <go> --map-tokens 0 --format text --db-path <db>`
- **Grading:** ground-truth citation (file + line + symbol), transcripts audited
  for ladder compliance and tool misuse
- **Metering:** agent-visible result-payload tokens (`utils.count_tokens`,
  tiktoken cl100k); directive text excluded; wall-clock not scored

## Leg order

1. **A-G5 repeat** (SSA: "Where does the Go compiler build SSA form for a
   function, and which function is the entry point?") — the leg where the
   58k junk query happened. Tests whether v1.3 exact-first kills that class.
   Ground truth: `src/cmd/compile/internal/ssagen/ssa.go:302 func buildssa`.
2. Further legs (G1/G3 repeats, B-legs) only after leg 1 is graded.

## Scope lock (2026-09-23)

The eval ASSUMES the mapping is done. It does NOT test the ability or
time to map (scan, rank, render) — it tests USING a prepopulated map
(detect/symbols/detail efficiency, agent-side). Prescan is sunk and
uncharged; serve-side speed is product work, out of scope for legs.
MAP-skip on Go is therefore not a workaround: rung-1 render cost is
mapping-time by this definition, and no pilot A-leg ever received a MAP
anyway. Legs measure retrieval given the index, nothing else.

## Deferred product work (NOT built mid-series — would move the ground)

- Ranks precompute: store unpersonalized PageRank in `file_ranks` at scan
  time (stamped with meta signature + extractor version), serve from the
  table when no personalization. Kills per-MAP power iteration.
- Map budget scaling: default budget `max(2048, n_files * R)` with
  tunable R (initial R=0.5 reproduces today's 8192 default at Go scale,
  floors small repos at 2048). Explicit `--map-tokens` always wins; legs
  keep passing explicit budgets.
- Both recorded here so they survive; build after the series.

## Records per leg (commit each)

- `v13/<leg>/transcript.md` — agent's commands in order + final answer
- `v13/<leg>/grade.md` — verdict, calls, tokens, compliance notes
- `GO-V13.md` updated cumulatively; `meter_go.py`-style metering per batch
