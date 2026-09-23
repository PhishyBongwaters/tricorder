# Leg A-G5 attempt 1 — ABORTED, no usable record from the agent

## What was sent (reconstructed verbatim from conversation history)

Model: `llamacpp/Qwen`. Foreground subagent, task "Go A-G5 leg under v1.3".

Prompt (paraphrase of DIRECTIVE.md v1+v1.3 — NOT verbatim; this is the
protocol violation):

- NL question: "Where does the Go compiler build SSA form for a function,
  and which function is the entry point?"
- Target repo, CLI path, warm DB path with "ALWAYS pass it, never rescan"
- v1.3 rules restated in own words: exact identifier guess first
  (`--detect`, `--max-results 10`), NL fallback capped at `--max-results 5`,
  junk-hit retry / never read junk, ladder after detect, stay in repo,
  every fact from a tool hit
- Hard 20-call cap, then answer with what you have
- Return: answer with citations, exact commands in order, per-command
  hit counts + usefulness

Deviations from DIRECTIVE.md v1 as-run (see main-session notes 2026-09-23):
rung 0 (`--init`) and rung 1 (MAP `--map-tokens 2048`) dropped; "1-2
wordings max" dropped; query discipline rewritten instead of quoted.

## Outcome

- Tool result: `Tool execution interrupted (sessionID:
  ses_f31e9687effelP6fXHoqQVM0SZ)`. No transcript returned.
- Operator observed repeated identical calls (suspected model tool-use
  loop on local Qwen — consistent with known local-model tool issues).
- Agent-side actions: UNRECOVERED. No transcript file exists; the
  interrupted session was not re-engaged (re-engaging risked more spam).

## Side-effect check (2026-09-23, read-only)

- Warm DB `bench_temp/eval-go-v13.db`: 1,402,044,416 bytes, mtime
  2026-09-23 8:46:31 AM. Cannot prove from this whether the agent wrote;
  no other conclusion drawn.
- `bench_temp/`: no new files besides the prescan DB (only two
  pre-existing Aug-30 entries alongside it).
- Repo worktree: `git status` clean, nothing modified.

## Process fix (locked)

No leg launches without its prompt already committed under
`eval/agent-eval-pilot/v13/<leg>/prompt.md`, quoted verbatim from
DIRECTIVE.md (v1 + deltas), approved by operator first. The prompt on
disk is the record even if the run explodes.
