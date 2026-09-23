# Leg B-G5 attempt 1 — PROMPT (committed before launch, operator approval required)

- Model: default (me — same model both sides, per pilot method).
- Question ONLY (no keywords, no ground truth — the agent discovers terms):
  "Where does the Go compiler build SSA form for a function, and which
  function is the entry point?"
- Cap: 20 tool calls, then answer with what you have.
- Completes the G5 A/B pair: A-G5 attempt 2 (PASS, 7 calls, 3,068 tokens)
  is recorded in `v13/leg-A-G5-attempt2/`.

## BASELINE RULES (mirror of the pilot's B-legs)

- Tools: file reads (exact line ranges only, never whole huge files
  blind — check size first), directory listings, and grep-style text
  search via shell. That is the complete kit.
- No tricorder CLI, no code-indexing or mapping tools of any kind. Stay
  inside the target repo: `D:\Projects\Tricorder-Testing-Repos\go`.
- No network, no installs.
- Every cited fact must come from something actually read (no guesses).
- Final answer MUST cite file path + line + symbol/function name.

## RETURN (for the record)

1. Answer with citations.
2. Exact commands run, in order.
3. Per command: what it returned (brief) + whether it looked useful.
