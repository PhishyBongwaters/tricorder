# Leg B-Vue-Q1 attempt 1 — PROMPT (committed before launch)

- Model: `llamacpp/Qwen` (local llama.cpp provider — same model as the
  A-leg, purest A/B).
- Question ONLY (no keywords, no ground truth — the agent discovers terms):
  "How does Vue implement its reactivity system — where are data properties intercepted, and how are dependent watchers notified of changes?"
- Cap: 15 tool calls, then answer with what you have.

## BASELINE RULES (mirror of the pilot's B-legs)

- Tools: file reads (exact line ranges only — check size first, never read
  whole huge files blind), directory listings, and grep-style text search
  via shell. That is the complete kit.
- No tricorder CLI, no code-indexing or mapping tools of any kind. Stay
  inside the target repo: `D:\Projects\Tricorder-Testing-Repos\vue`.
- No network, no installs.
- Every cited fact must come from something actually read (no guesses).
- Final answer MUST cite file path + line + symbol/function name.

## RETURN (for the record)

1. Answer with citations.
2. Exact commands run, in order.
3. Per command: what it returned (brief) + whether it looked useful.
