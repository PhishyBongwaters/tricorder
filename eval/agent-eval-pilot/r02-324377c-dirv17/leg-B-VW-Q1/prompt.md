# Leg B-VW-Q1 — PROMPT (committed before launch, operator approval required)

- Model: `llamacpp/Qwen` (local llama.cpp provider, `Qwen3.6-35B-A3B-UD-Q4_K_M.gguf`).
- Question ONLY (no keywords, no ground truth — the agent discovers terms):
  "Where is TOTP two-factor code verification implemented?"
- Cap: 15 CLI calls, then answer with what you have.
- Target repo: `D:\Projects\Tricorder-Testing-Repos\vaultwarden`.
- BASELINE arm: grep / ripgrep, file reads, glob only. NO tricorder
  (no `--detect`, `--symbols`, `--map`, `--smart-map`, no DB).
  Stay in the target repo.
- Save every tool result payload to `step_<name>.txt` in this folder and
  maintain `transcript.md` (cmd, step, result summary). Final answer must
  cite file + line + symbol, every fact from a tool hit, no guesses.
