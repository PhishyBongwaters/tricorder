# SPEC T2 — smart-map identifier-first (skip that fires on NL questions)

Status: SPEC ONLY (unbuilt). Ordered 2026-09-25 from r03 leg-5 log evidence.

## Problem

v1.7 smart-map skips MAP only on an exact hit from ONE
`search_identifiers(QUERY, max_results=5)` call — but rung 1 receives
the raw NL question, which can never exact-hit. On Rails (under 5000
files) the MAP therefore ALWAYS runs: leg 5 paid a 7.2k-char MAP whose
head was minified noise (see SPEC T1). The question literally contained
`` `has_many` `` in backticks; nothing tried it. Exact-first (v1.3)
stops at rung 2's door.

## Constraints

- The skip must stay conservative: a wrong skip denies the agent the
  MAP (VW-Q1-att1's MAP answered — skips must not regress that class).
  Skip ONLY on quality=="exact" hits, as today; this spec only widens
  WHAT gets tried, never the skip bar.
- Deterministic, stdlib-only, no LLM. Bounded probes (the skip path
  must stay an order of magnitude cheaper than the MAP it avoids).
- MCP `smart_map` and CLI `--smart-map` share the code path
  (`SMART_MAP_MAX_FILES` single source stays).

## Proposed mechanism

Before falling through to MAP, derive identifier candidates from the
query IN ORDER and try each as an exact `search_identifiers(cand,
max_results=5)`; first exact hit skips MAP exactly as today:

1. Backticked spans (`` `has_many` ``) — highest signal, author-marked.
2. Bare `Class::method` / `Class.method` / `snake_case` / `camelCase`
   tokens (length ≥ 3, not in CODE_QUERY_STOPWORDS).
3. Stop after the first candidate that exact-hits; cap total candidates
   tried (suggest ≤ 3) so the skip path stays cheap.

If none exact-hits → today's behavior (MAP as written) byte-for-byte.

## Acceptance (red-first)

- `tricorder --smart-map "How does ActiveRecord implement the
  \`has_many\` association..."` on Rails skips MAP (output has detect
  results, no `map` key / no fitted tag list); pre-fix it runs MAP.
- Leg-5 replay: rung-1 cost drops from ~7.2k chars to probe + 1–3
  exact probes; answer still reachable (detect `has_many` unchanged).
- No-skip regressions: VW-Q1-att1 shape (MAP answered) still runs MAP
  when no candidate exact-hits; full suite green.
- MCP parity test: `smart_map` skips identically for the same query.

## Non-goals

- NL understanding (no keyword extraction beyond identifier shapes).
- Changing the skip bar (exact-only stays).
- Directive text (rung-1 input wording is a v1.9 matter, separate).
