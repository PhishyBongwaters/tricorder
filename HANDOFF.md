# TRICORDER — SESSION HANDOFF (2026-09-28, current)

Fresh session? Read this file only — no re-derivation. Confirm you've
read it and state tree status before doing anything else.

## Environment (verified)

- Worktree `D:\Projects\tricorder`, branch `main`, github remote
  (`git@github.com:PhishyBongwaters/tricorder.git`) is source of truth;
  `git push github main` per step. `origin` = gitea via hermes-agent
  (unreachable) — never fetch/push it.
- Suite green: **543 passed, 4 skipped, 98 subtests**
  (`.venv/Scripts/python.exe -m pytest tests/ -q -p no:cacheprovider`).
- PowerShell: no `head/tail/grep/sed/&&`; use `Select-Object -First N`,
  `Select-String`, `;`. `>` redirect writes UTF-16 — use `--output` or
  explicit utf8 writes for byte-compares.
- Untracked scratch NOT ours — never touch, never commit:
  `docs/*.proposed.md`, `docs/SPEC_readme_rewrite.md`,
  `docs/process*.md`, `docs/retrieval.md`, `docs/issue-*.md`, `spikes/`.
- Models: operator model (muse-spark, disciplined vehicle, default for
  subagents — never pass `model` unless told); `llamacpp/Qwen` only when
  explicitly ordered for Qwen legs.
- **Another agent session works in this tree.** Check `git log` +
  `git status` for foreign commits/dirty files before acting. NEVER
  touch, commit, or revert work that isn't yours. Concurrent scans
  contend on sqlite; parallel subagents rate-limit — one foreground
  subagent at a time, no background loops.

## Product (all landed, suite-green; HEAD `c5613d8` + eval commits)

- `--smart-map`/MCP `smart_map` (threshold `SMART_MAP_MAX_FILES=5000`,
  `utils.py`); `--mention` (10x idents / 5x files); Qwen legs infra.
- Serve perf: render memo, warm-clean serve gate skips `populate_refs`,
  one-time `file_ranks` backfills on canonical DBs. Go MAP ~6s, Rails ~2s.
- Rescue keyword strip (`CODE_QUERY_STOPWORDS`); neutral probe digest
  with discovery counter parity.
- **T1** (`bba4a58` + mechanism-2): fixture/testdata + fingerprinted
  assets + minified-blob content sniff excluded at discovery (serial +
  threaded + probe; ctags fixture excludes). Tests
  `test_t1_fixture_exclusion.py`, `test_t1b_minified_sniff.py`.
- **T2** (`144aa54`): smart-map identifier-first
  (`smart_map_candidates` + `smart_map_exact_hit`, exact-mode probes,
  cap 3, skip bar quality==exact). Bare-token filter uses NL stopwords
  too (disclosed deviation). Test `test_t2_smartmap_identifiers.py`
  (+2 CLI-text tests from concurrent session fixing a real KeyError).
- **T3** (`47e57a8`): symbols boundary rank + test-path demotion.
  **T4**: rescue-hit ranking (deterministic variants, no early break).
  Test files `test_t3_symbols_priority.py`, `test_t4_symbols_rescue.py`.
- **Transcript items** (from r05/r06 A-leg trails): #1 symbols diet
  (`compact_symbol_record`, -23% bytes; 9-field contract updated);
  #2 DROPPED (5x boost can't cross 16x rank gaps — live negative);
  #3 detect test-path demotion; #4 MAP dedup + 4dp ranks.
- **Extractor dedup** (`c6963ba`): column-aware emission dedup in
  `parser.get_tags_raw` (HCL 4x collapse; chained-call repeats kept).
  Test `test_extractor_dedup.py`.
- Analysis tools: `eval/agent-eval-pilot/tools/` (README indexes all).

## Eval method (frozen — do not relitigate)

- Harness truth: `opencode.db` session rows (`mode=ro`). Meter legs
  from session rows (ID at launch); grade from message contents; agents
  save NOTHING; self-reports are never metering (agents undercount
  1–2 calls routinely — 3 of 4 legs).
- **Scored = peak context/call** (fresh + re-reads; EVAL-PROCESS as of
  `c5613d8`). Billing primary tabled as context, never verdict.
  TRUE-TALLY.md stands unedited (historical).
- **1 run per question per repo; re-runs only on change.** No repeats
  without explicit operator order, ever. (A unilateral n=3 scheme was
  revoked 2026-09-27; extras marked supplementary in r05/r06.)
- Prompts committed BEFORE launch; legs sequential; grade+commit per
  leg (grade.md + README row, `.txt` artifacts rule inherited);
  session DB snapshotted to `eval/agent-eval-pilot/opencode-YYYY-MM-DD.db`
  as legs land (latest: 2026-09-28).
- NEVER unilaterally: void legs/rounds, re-scope rounds, rewrite
  history, change the metric, add process gates. Findings to operator;
  ALL judgment calls are the operator's. Stop-the-line rule: code or
  directive moves → new round, stale legs never mix.
- Coverage = `COUNT(*) FROM file_state`; `meta` exactly 1 row;
  `--max-files` is a PREFIX cap (rising caps only); never hardcode
  repo paths; never connect a possibly-absent DB; no destructive
  commands (canonical-DB wipes need backup + explicit order).

## Rounds (valid scores only)

- v13 TRUE-TALLY: paired 0.74×; firm wins Q3 0.13× / Q4 0.07×.
- r03 (v1.8): HOLD at 5/12 — no legs without operator approval.
- r04: Rails pair scored (context 0.85× inv); VW legs MOVED to r06.
- r05 (T4 build, v1.9): Rails valid **0.85× inversion** (A 19,480 /
  B 22,783 peak ctx). Extras supplementary.
- r06 (T4 build, v1.9): VW valid **1.45× inversion** (A 19,366 / 9
  calls vs B 13,340 / 3 calls). Extras supplementary.
- DIRECTIVE v1.10 committed (flag discipline, skip-is-rung2) — NO
  ROUND RUNS IT YET. Next legs need a v1.10 round folder.
- No MCP-surface legs ever (coverage gap). Plugins unported (TBD).

## Comms (do without being asked twice)

- Milestones unprompted via `hermes send --to discord:phishybongwaters`
  AND `--to telegram:phishybongwaters` (leg graded, round changes,
  suite red/green, blocked/waiting, ready-for-orders).
- Keep THIS file current — state, commits, open threads.

## Remaining (operator decides, no implied order)

1. **Canonical rebuilds** (deferred by order): purge 855 dupe rows +
   settle all DBs on current code (backup → wipe → chunk_resume →
   backfill → verify). Rails/Go/VW minimum. Rescale
   `tools/verify_backfill.py` wants after.
2. **v1.10 round**: VW and/or Rails pair under the amended directive
   (first test of flag discipline + skip-is-rung2).
3. **Go on current build** (r03's 0.60× is pre-everything); Elixir/Vue/
   Swift DBs settled, unmeasured recently.
4. **Parked**: quality-`"exact"` overclaim (moves only with a T2-aware
   spec); get_symbols/HCL garbage (grammar quality, no leg impact).
5. r03 legs 6–12 still on hold; r03-vs-new comparisons are confounded
   (state it every time, never quote cross-build deltas as effects).
