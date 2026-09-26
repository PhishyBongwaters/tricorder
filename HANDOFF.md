# TRICORDER — FRESH SESSION HANDOFF (2026-09-26)

## Environment (verified, do not re-derive)

- Worktree: `d:\projects\tricorder`, branch `main`, in sync with github
  remote (`git@github.com:PhishyBongwaters/tricorder.git` — source of
  truth, `git push github main` per step). `origin` = gitea via
  hermes-agent (unreachable from here) — never fetch/push it.
- Suite green: **508 passed, 4 skipped, 98 subtests**
  (`python -m pytest tests/ -q -p no:cacheprovider`, repo `.venv`).
- Shell is PowerShell: NO `head/tail/grep/sed/&&` — use
  `Select-Object -First N`, `Select-String`, `;` separators.
  `>` redirect writes UTF-16 (matters for token metering).
- Untracked scratch NOT mine — never touch, never commit:
  `docs/*.proposed.md`, `docs/SPEC_readme_rewrite.md`,
  `docs/process*.md`, `docs/retrieval.md`, `docs/issue-*.md`, `spikes/`.
- Local model for eval legs: `llamacpp/Qwen`
  (`Qwen3.6-35B-A3B-UD-Q4_K_M.gguf`, 16GB VRAM target). Operator model
  (me/muse-spark) is the disciplined vehicle. Default subagent model =
  operator model; pass `model="llamacpp/Qwen"` explicitly for Qwen.

## Where the project stands (main @ `bbd894a` after this handoff's commit)

Product (all landed, suite-green, byte-identical outputs where claimed):
- `--smart-map` / MCP `smart_map` (v1.6–v1.7, threshold
  `SMART_MAP_MAX_FILES=5000` in `utils.py`); `--mention` flag; Qwen legs.
- Serve-perf fixes: per-render file-text memo (`core.py`/`render.py`,
  thread-local, test `test_render_reread.py`); serve gate — warm-clean
  + fresh ranks skips `populate_refs` (`ranking.py`, tests in
  `test_file_ranks.py::TestWarmServeSkipsRepopulate`); one-time
  `file_ranks` backfills on Go/Rails/VW/Vue/Elixir/Swift canonical DBs
  (additive tables only). Go MAP: timeout → 6s steady; Rails 2s.
- Rescue keyword strip (`CODE_QUERY_STOPWORDS` + `rescue_query_tokens`,
  both detect mirrors; test `test_rescue_stopwords.py`) — from the
  Go-G5 loop autopsy (150× identical `ssa.Main` query).
- Probe digest neutral tail + counter parity with discovery
  (`utils.probe_project`/`format_probe_digest`, test
  `test_probe_digest.py`). NOTE: legs that ran before `fb2ef95` saw the
  old MCP/slash tail in probe output.
- Eval analysis tools (tracked): `eval/agent-eval-pilot/tools/`
  (`ocdb/ocmsg/ocmap/occtx/octools/ocover/ocpeak/oploop/ocleg/ocassess/ocdiverge`
  = session-DB forensics; `audit_legs.py`; `backfill_ranks.py`;
  `*-inv.py`, `go_*.py`, `vw_comp.py`, `dbg_*.py` = trails). README indexes all.

Eval state:
- Regime docs: `eval/agent-eval-pilot/DIRECTIVE.md` (v1.8 current:
  5000+ repos skip rung-1 MAP), `QUESTIONS.md` (canonical six + depth
  panel + scripted note), `EVAL-PROCESS.md`.
- `v13/TRUE-TALLY.md` — v13 re-measured from harness truth: paired
  aggregate **0.74×** (published 0.30× artifact tally stands
  unedited beside it). Inversions: VW-Q1 + both VW-Q2 (greppable
  questions lose); big wins Q3 (0.13×) Q4 (0.07×). RUNLOG aggregate
  line doesn't match its own table (noted, not repaired).
- r03 (`r03-46d32c1-dirv18/`, operator-model vehicle, v1.8): 5/12 legs
  scored — Go-G5 0.60×, VW-Q1 0.50×, Rails-Q1 A (25,289, no B yet).
  **HOLD: no legs past leg 5 without operator approval** (in r03 README).
- Ad-hoc (NOT rounds): `map-vs-detect/` (parked — Qwen looped 212
  tools; 2 aborted sessions recorded excluded), `qwen-b-g5/` (PASS,
  48,072 truth, 0 repeats — Qwen CAN run clean on baseline).
- UNBUILT SPECS (this handoff's commit): `docs/SPEC-minified-fixture-exclusion.md`
  (T1, severe: minified fixtures PageRank-bomb MAP heads),
  `docs/SPEC-smartmap-identifier-first.md` (T2: skip never fires on NL
  questions — try backticked/identifier tokens first),
  `docs/SPEC-symbols-definition-priority.md` (T3: test classes crowd
  definition sites out of top-5).
- v1.9 ideas (NOT approved, do not build): rung-1 takes identifier
  input; rung-4 mechanism naming; doc-walk rule; context-ceiling per
  leg; harness loop breaker (not buildable here — harness-side).

## The method (harness truth — this replaces ALL artifact metering)

- `opencode.db` (`C:\Users\macdo\.local\share\opencode\opencode.db`,
  ALWAYS open `mode=ro`): `session_v2` =
  per-session input/output/reasoning/cache_read/write + model + title +
  parent link; `session_message` = per-message tokens + full tool
  contents (commands AND returns; oversized spill to `tool-output/`).
- Meter legs from session rows (ID recorded at launch). Grade/audit
  from message contents. Agents save NOTHING (no step files).
- Behavior now exactly measurable: first-hit vs stop call
  (over-verification priced — leg-3-style: 8% to answer, 92% after),
  repeats, ladder order, junk handling.
- Tokenizer: provider-native units (no tiktoken estimation anymore).
- Model comparison baseline: Qwen costs ~2–4× operator model same arms;
  Qwen-matched Go pair ≈0.98× vs operator-matched 0.60×.

## House rules (violations caused the 2026-09-25 blowup — obey literally)

- Red-first: failing test before every fix; full suite after every
  product change; commit + push per step to github.
- Eval: prompts committed BEFORE launch; ONE foreground subagent at a
  time (parallel launches rate-limit); meter from session rows;
  transcript+grade+artifacts committed; `.txt` extensions only.
- NEVER unilaterally: void legs/rounds, add process gates, rewrite
  history, re-scope rounds, or "fix" the process. Findings to operator;
  ALL judgment calls (void, re-run, round, stop) are the operator's.
  Token savings is the only scored metric; counts are context, never
  verdicts. Cap = leash (termination), not score.
- No destructive commands without explicit approval. No background loops.
- Coverage = `COUNT(*) FROM file_state`, never tags-distinct.
  `meta` holds exactly 1 row. `--max-files` is a PREFIX cap (rising
  caps only). Never hardcode repo paths in app code. Never
  `sqlite3.connect` a possibly-absent DB.
- Savings numbers cite the committed run that produced them. No MCP-surface
  eval legs have ever run (coverage gap). MCP server + turn-0 plugins
  unported — TBD, no usage claims.

## Comms (operator preference — do this without being asked twice)

- Proactive Discord/Telegram updates at milestones (leg graded,
  round state changes, suite red/green on product work, blocked/waiting)
  so the operator doesn't have to sit at the keyboard. Verified
  2026-09-26: `hermes send --to discord:phishybongwaters "msg"` and
  `hermes send --to telegram:phishybongwaters "msg"` (targets listed
  via `hermes send --list`; bot-token platforms need no running
  gateway). Use freely.
- Session continuity: keep HANDOFF.md current (state, commits, open
  threads) — a fresh session starts by reading it, no re-derivation.

## Likely next steps (operator decides, in no implied order)

1. Legs 6–12 of r03 (on hold) — or close r03 as a 5-leg partial.
2. Build SPECS T1–T3 (any order; each red-first + suite + commit).
3. v1.9 directive items if operator wants them (new round required).
4. Swift canonical DB is settled (13s MAP steady); Elixir/Vue canonical.
