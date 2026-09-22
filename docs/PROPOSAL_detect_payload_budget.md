# Proposal: Budget `tricorder_detect` / `--detect` Payloads

> **Implemented.** `max_tokens` on `tricorder_detect`/`tricorder_symbols`
> (+ CLI `--max-tokens`), backed by `utils.enforce_search_budget`
> (context/docstring first, then tail hits; `truncated`/`total`/`omitted`).
> Pinned by `tests/test_detect_budget.py` (8 tests). Kept as design record.

## Problem

`tricorder_detail` got `max_tokens` (trim body → callees → callers, never
identity). `tricorder_detect` has no equivalent: one fuzzy natural-language
query can return an unbounded JSON payload.

**Evidence (agent-eval pilot, `eval/agent-eval-pilot/GO.md`):** A-G5's first
query ("build SSA form for function") matched junk JS hits costing **58,624
tokens** in a single response — 50× the leg's clean cost (1,093) and the
costliest step in the batch. The agent self-corrected and passed, but the
spend was already sunk. Directive rules (exact-first, capped first passes)
reduce the odds; only a server-side budget removes the class — same
unbudgeted-output wart `detail` had before `_final_budget_check`.

## Options

1. **`max_tokens` param on detect/symbols** (mirror `detail`): trim order —
   drop per-hit context first (keep file/line/name/quality identity), then
   drop lowest-ranked hits, reporting `truncated` + `total`/`omitted`
   counts like detail's `callers_total` convention.
2. **Per-hit context cap**: bound context chars per hit; cheap, no API
   change, but a fixed cap still allows N-hits × cap blowups.
3. **Both**: (2) as the default guardrail, (1) for explicit budgets.

CLI `--detect`/`--symbols` inherit via the existing `--format` path.

## Acceptance

- Red test first: the A-G5 NL query against a Go-scale index stays under
  the budget (payload ≤ budget, identity of top hits preserved,
  `truncated` set).
- Full suite green; MCP/CLI reference docs updated for the new param.
- Out of scope: changing ranking itself (that's `090456e` territory,
  already shipped); this is purely output budgeting.
