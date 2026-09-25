# Leg B-Go-G5 — PROMPT (committed before launch, operator approval required)

- Model: default (operator's model).
- Question ONLY (no keywords, no ground truth — discover terms yourself):
  "Where does the Go compiler build SSA form for a function, and which
  function is the entry point?"
- Cap: 20 tool calls, then answer with what you have.
- Target repo: `D:\Projects\Tricorder-Testing-Repos\go`.
- BASELINE arm: grep / ripgrep, file reads, glob only. NO tricorder
  (no CLI, no `--detect`, no DB). Stay in the target repo.
- NEVER issue the identical tool call twice in a row: if a result does
  not advance you, change the terms (new words, narrower scope) or move
  on. Repeating a dead query is failure.

## Bookkeeping: NONE

Save NOTHING to disk (no step files, no transcript). Every call and
result is logged harness-side. Finish with your answer (file + line +
symbol per fact, no guesses), then report back: answer, calls used.
