# SPEC T3 — symbols definition-site priority over test classes

Status: SPEC ONLY (unbuilt). Ordered 2026-09-25 from r03 leg-5 log evidence.

## Problem

`symbols "HasMany"` (max_results 5) returned five test classes
(`AsyncHasManyAssociationsTest`, `Deprecated…`, model fixtures…) —
`builder/has_many.rb` (`Builder::HasMany`, the definition site) absent
entirely. The agent correctly ignored all five and found the builder
via detect+grep, but rung 3 burned ~2.8k chars to say nothing usable.
On test-heavy repos, substring matches against `*Foo*Test` classes
crowd definition sites out of the capped budget.

## Constraints

- Some questions ARE about tests — never exclude test paths, only
  deprioritize. A test-file hit must still be reachable (cap tail).
- Deterministic, stdlib-only. Shared by CLI `--symbols` and MCP
  `tricorder_symbols` (same function — verify).
- No regression on existing symbols tests + language matrix.

## Candidate mechanisms (pick one at build time)

1. **Word-boundary rank-up**: candidates where the query matches a full
   camel/snake word (`HasMany` in `Builder::HasMany`) sort above pure
   superstring matches (`…HasMany…Test`). Minimal, language-agnostic,
   no path heuristics.
2. **Test-path demotion**: paths under `test/`, `spec/`, `*_test.*`,
   `test_*` sort below same-score non-test hits (never excluded).
   Stronger effect on Rails-class repos; encodes a repo-layout prior.
3. **Both**: boundary first, test-path as tiebreak. Recommended if (1)
   alone leaves test classes interleaved ahead on real repos.

## Acceptance (red-first)

- `symbols "HasMany"` on Rails includes `builder/has_many.rb` in top 5
  (any position beats absent); test classes may remain in the list.
- Full suite green, especially symbols/listing tests.
- Spot-check other repos' symbols outputs for test-demotion damage
  (none expected: demotion, not exclusion; boundary is additive rank).

## Non-goals

- Test-file exclusion (explicit non-goal — test questions exist).
- Semantic relevance ranking (no LLM, no IDF here; keep it orthographic).
