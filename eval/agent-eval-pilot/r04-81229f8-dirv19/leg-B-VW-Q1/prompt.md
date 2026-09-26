# Leg B-VW-Q1 — PROMPT (committed before launch)

- Model: default (operator's model).
- Question ONLY (no keywords, no ground truth — discover terms yourself):
  "Where is TOTP two-factor code verification implemented?"
- Cap: 15 tool calls, then answer with what you have.
- Target repo: `D:\Projects\Tricorder-Testing-Repos\vaultwarden`.
- BASELINE arm: grep / ripgrep, file reads, glob only. NO tricorder
  (no CLI, no `--detect`, no DB). Stay in the target repo.
- NEVER issue the identical tool call twice in a row. If 3 consecutive
  tool results do not advance you toward an answer file/symbol, STOP
  searching and answer with what you have.

## Bookkeeping: NONE

Save NOTHING to disk (no step files, no transcript). Every call and
result is logged harness-side. Finish with your answer (file + line +
symbol per fact, no guesses), then report back: answer, calls used.
