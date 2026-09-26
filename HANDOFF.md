# TRICORDER — FRESH SESSION HANDOFF (2026-09-26, evening)

## Environment (verified, do not re-derive)

- Worktree: `d:\projects\tricorder`, branch `main`, in sync with github
  remote (`git@github.com:PhishyBongwaters/tricorder.git` — source of
  truth, `git push github main` per step). `origin` = gitea via
  hermes-agent (unreachable from here) — never fetch/push it.
- Suite green: **534 passed, 4 skipped, 98 subtests**
  (`python -m pytest tests/ -q -p no:cacheprovider`, repo `.venv`).
  Was 508 at session start; +26 = T1 (2) + T1-mechanism-2 (2) + T2 (11:
  6 candidates + 3 probe-loop + 2 MCP + 2 CLI-text) + T3 (6) + T4 (3)
  new tests. (The 2 CLI-text tests + text-mode fix arrived via the
  concurrent session, verified green here before commit.)
- Shell is PowerShell: NO `head/tail/grep/sed/&&` — use
  `Select-Object -First N`, `Select-String`, `;` separators.
  `>` redirect writes UTF-16 (matters for token metering; use
  `--output` flag or explicit utf8 writes for byte-compares).
- Untracked scratch NOT mine — never touch, never commit:
  `docs/*.proposed.md`, `docs/SPEC_readme_rewrite.md`,
  `docs/process*.md`, `docs/retrieval.md`, `docs/issue-*.md`, `spikes/`.
- Local model for eval legs: `llamacpp/Qwen`
  (`Qwen3.6-35B-A3B-UD-Q4_K_M.gguf`, 16GB VRAM target). Operator model
  (me/muse-spark) is the disciplined vehicle. Default subagent model =
  operator model; pass `model="llamacpp/Qwen"` explicitly for Qwen.
- Live-check scratch pattern (used T1–T3, keeps canonical DBs clean):
  copy canonical DB to `C:\Users\macdo\AppData\Local\Temp\opencode\`,
  pass `--db-path <copy>` + `--root <real repo>`; `git stash push
  <files>` for pre-fix baselines, `git stash pop` after. `--init`
  ignores `--db-path` (always writes canonical) — check for stray
  `.tricorder/db/<name>.db` after scratch scans and delete.

## Where the project stands (main @ `a31fe08`; T1-mechanism-2 latest)

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
- **T1 BUILT (`bba4a58`)**: fixture/testdata + fingerprinted-asset
  exclusion from discovery (`_FIXTURE_SKIP_DIRS`,
  `_HASH_ASSET_RE`, `_is_fixture_or_hash_asset` in `utils.py`; serial +
  threaded + probe paths; ctags fixture-dir excludes). Test
  `tests/test_t1_fixture_exclusion.py`. Live: old MAP head `$`/`q`
  from Rails fixture bomb → new shows only real defs; VW/Go MAP bytes
  identical pre/post. Deliberate recall edge: files UNDER exact-named
  `fixtures/` dirs are dropped (documented miss); `*_fixtures`-named
  dirs (`autoloading_fixtures/`, `controller_fixtures/`) and the
  fixtures FRAMEWORK source (`fixtures.rb`, `fixtures_test.rb`) are
  KEPT (name-contains, not path-segment).
- **T2 BUILT (`144aa54`)**: smart-map identifier-first
  (`smart_map_candidates` + `smart_map_exact_hit` in `utils.py`,
  shared by CLI `--smart-map` and MCP `smart_map`; probes use
  `search_mode="exact"`, skip bar unchanged at quality==exact, cap 3).
  Test `tests/test_t2_smartmap_identifiers.py` (unit + MCP skip +
  fallthrough). Live Rails-Q: pre 6,298-char noise MAP → post
  2,143-char detect skip headed by `def has_many`
  (associations.rb:1426); VW-Q1 MAP byte-identical pre/post.
  DISCLOSED DEVIATION: bare-token filter excludes NL_QUERY_STOPWORDS
  too (SPEC named CODE only) — otherwise `the`/`and`/`what` become
  skip probes and a tag literally named `the` would wrongly deny MAP.
- **T3 BUILT (`47e57a8`)**: symbols definition-site priority
  (`symbol_boundary_rank` in `utils.py`: 0 full-name, 1 `::`-segment,
  2 superstring; `is_test_file` demotion as tiebreak; both prepended
  to the main-path sort in `core.search_symbols`, rescue sorts
  untouched). Test `tests/test_t3_symbols_priority.py`. Live Rails
  `symbols HasMany`: old top-5 all test classes → new headed by
  `builder/has_many.rb`, test classes at #14–15/39 (reachable).
  Spot-checks: VW identical membership (reorder only); Go displaced
  only test-path hits. CLI `--symbols` + MCP `tricorder_symbols`
  share the path (verified by grep).
- **T4 BUILT (operator-ordered tweak)**: symbols rescue-hit ranking
  (`core.search_symbols` rescue tiers only): deterministic
  specific-first variant order (query forms, then longest, alpha —
  the variant set's iteration order varied per process and the old
  `limit*2` early break let one variant saturate the pool before
  better variants ran, so definitions were never collected); rescue
  re-sort prepends the T3 keys (boundary, test-demotion) before
  distance; early break removed (pool is a superset now, trimmed to
  cap at the end). Test `tests/test_t4_symbols_rescue.py`. Live leg-A
  call (`symbols Builder::HasMany`): old fuzzy head
  `AsyncHasManyAssociationsTest` → new head `HasMany`
  (builder/has_many.rb), zero test files in top-5. Spot-checks: VW
  rescue query byte-identical top-10; Go displaced only test-path
  hits. `search_identifiers` rescue untouched (rung-2 contract).
- Eval analysis tools (tracked): `eval/agent-eval-pilot/tools/`
  (`ocdb/ocmsg/ocmap/occtx/octools/ocover/ocpeak/oploop/ocleg/ocassess/ocdiverge`
  = session-DB forensics; `audit_legs.py`; `backfill_ranks.py`;
  `*-inv.py`, `go_*.py`, `vw_comp.py`, `dbg_*.py` = trails). README indexes all.

Canonical DBs (rebuilt 2026-09-26 evening, operator-ordered):
- **Rails REBUILT**: `--init --wipe` + `chunk_resume.py` (one chunk,
  3932/3932) + `backfill_ranks.py` (45s, fresh=True). Backup of pre-T1
  DB at `C:\Users\macdo\AppData\Local\Temp\opencode\rails-pre-t1-backup.db`
  (809MB — temp, will age out; re-backup before any further wipe).
  Before → after: file_state 4470 → 3932; tags 727,607 → 722,111;
  refs 4,245,851 → 3,863,755; file_ranks 3490 → 3456; fixture tags
  10,080 → 4,584 (remainder = fixtures FRAMEWORK source, kept by
  design — see T1 note); gzip bomb 0 tags/0 files; hash-assets 0.
  `meta` 1 row, extractor v3. `verify_backfill.py` rails want
  rescaled 3490 → 3456 (committed with this handoff).
- **Rails REBUILT AGAIN (mechanism-2, same evening)**: `_is_minified_blob`
  drops `guides/assets/.../clipboard.js` → file_state 3932 → 3931,
  file_ranks 3456 → 3455, fresh=True. Backup of post-T1 DB at temp
  `rails-post-t1-backup.db`. Rebuilt MAP head (2048 budget) is
  `ActionDispatch::Routing::Mapper` — zero single-char defs. The
  clipboard.js OPEN FINDING below is CLOSED. `verify_backfill.py`
  rails want rescaled 3456 → 3455.
- Go/VW/Vue/Elixir/Swift DBs UNTOUCHED (T1–T3 proved byte-identical
  MAPs there; no rebuild needed). Go `verify_backfill` shows
  ranks=10766 vs want 10736 — pre-existing repo drift, not ours.
- **OPEN FINDING (measured, not fixed)**: post-rebuild Rails MAP head
  is STILL minified noise — `guides/assets/javascripts/clipboard.js`
  single-char defs (`a`,`b`,`c`…) at file-rank 0.027, top of MAP.
  T1 acceptance was fixture-paths-only so T1 stands, but this is the
  SPEC's deferred mechanism-2 trigger ("content sniffing … only if
  measured MAP-head pollution persists"). CLOSED 2026-09-26 evening:
  mechanism 2 built, clipboard.js excluded, MAP head verified real
  source (see Rails REBUILT AGAIN above). Fix needs no further call.

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
  Operator 2026-09-26: new legs start on the post-rebuild commit
  once handoff + rebuild sorted (this handoff). Rails-Q1 leg-5 ran
  pre-T1/T2/T3 on the OLD rails.db — its MAP-side costs are stale
  relative to the new DB + skip behavior; flag before comparing.
- Ad-hoc (NOT rounds): `map-vs-detect/` (parked — Qwen looped 212
  tools; 2 aborted sessions recorded excluded), `qwen-b-g5/` (PASS,
  48,072 truth, 0 repeats — Qwen CAN run clean on baseline).
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
  Canonical-DB wipes are destructive: backup to approved temp first,
  operator order required (granted 2026-09-26 for Rails).
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

1. New legs on post-rebuild commit (operator-ordered; r03 legs 6–12
   still on hold separately — clarify whether new legs = r04 or
   r03-continued before launching anything).
2. clipboard.js MAP-head pollution: mechanism-2 content sniff, narrow
   name rule, or leave-and-route-around (operator call; red-first +
   suite + commit if build).
3. v1.9 directive items if operator wants them (new round required).
4. Swift canonical DB is settled (13s MAP steady); Elixir/Vue canonical.
