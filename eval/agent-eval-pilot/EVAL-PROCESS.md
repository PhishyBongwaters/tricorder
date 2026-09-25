# Agent-eval process (how rounds run)

## Roles

- **Operator** (me): commits prompts before launch, spawns subagents,
  meters, grades, commits results, sends Discord updates when asked.
- **Agent vehicle**: one foreground subagent at a time (parallel launches
  rate-limit). Model: local `llamacpp/Qwen`
  (`Qwen3.6-35B-A3B-UD-Q4_K_M.gguf`, 16GB VRAM target — token savings
  for this class of model is the point of the series). No skills loaded;
  the frozen directive copy in the round folder IS the instrument.
- **Arms**: A-leg (tricorder CLI, directive ladder) vs B-leg (same
  question, same cap, grep/read/glob only, stay in target repo).

## Build = directive + code

A round freezes BOTH: the code commit (folder name carries the short
SHA) and the directive version (frozen copy in the round folder; legs
quote it verbatim). Either one moving starts a new round.

## Round lifecycle

1. **Freeze**: directive version bumped if needed, regime docs current,
   everything committed + pushed. Round folder:
   `eval/agent-eval-pilot/rNN-<shortsha>-dirv<MM>/` with frozen
   `DIRECTIVE.md`, round `README.md` (code commit, model filename,
   meter version, repo revisions), and per-leg folders.
2. **Leg setup**: prescan/settle each repo DB once (sunk, uncharged,
   timed and recorded — first MAP after drift can exceed the agent
   timeout; rung 0 `--init` covers this). Warm DB stated in the prompt.
3. **Prompt**: committed BEFORE launch. Question text ONLY (no keywords,
   no ground truth), cap (15 calls; 20 on 10k+ file repos), verbatim
   directive quote, model, repo + DB path.
4. **Run**: one foreground subagent per leg. Transcript saved.
5. **Meter**: `v13/meter_leg.py` (agent-visible result-payload tokens,
   tiktoken cl100k; directive text excluded; wall-clock not scored).
   `.txt` extensions only for artifacts (parseable extensions break
   `test_empty_result`).
6. **Verify (metering-integrity gate, 2026-09-25)**: BEFORE metering,
   the operator counts `step_*.txt` files against transcript rows. Any
   tool call without a saved verbatim payload → the leg's token total
   is VOID (citation/compliance findings may stand as behavioral data).
   Void legs are re-run as new attempts; void cells never enter tallies.
   The agent prompt carries the save-everything instruction as its
   highest-priority order, including the void consequence.
6. **Grade**: ground-truth citation (file + line + symbol) from
   `QUESTIONS.md`; ladder-compliance audit; `grade.md` committed with
   tokens table.
7. **Tally**: per-round README keeps A/B tokens + calls; grand tallies
   cite the rounds that produced them, never mix across builds.

## Stop-the-line rule

Bug found mid-round → HALT the round. Fix on main (red-first, suite,
commit+push per house rules), then start a NEW round folder on the new
commit and re-run from leg 1. Stale legs never mix across code versions.
Same for directive edits: new version, new round.

## What never happens

- No background leg loops (the user kills them); no parallel subagents.
- No MCP-surface claims without MCP-surface legs (coverage gap, open).
- No destructive commands (rm, wipes) without explicit approval.
- No savings numbers without the committed run that produced them.
