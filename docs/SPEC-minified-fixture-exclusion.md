# SPEC T1 — minified / fixture exclusion from tagging

Status: BUILT 2026-09-26 (commit on main; mechanisms 1+3).
Ordered 2026-09-25 from r03 leg-5 log evidence.

## Problem

r03 A-Rails-Q1's rung-1 MAP (7,190 chars) was headed by single-char
"defs" (`$`, `A`, `B`, `CHILD` …) from
`actionpack/test/fixtures/public/gzip/application-a71b3024f80aea3181c09774ca17e712.js`
at PageRank 0.034 — the top of the Rails MAP. A gzipped fixture parsed
into hundreds of fake symbols that cross-reference each other: a
PageRank bomb. `_MINIFIED_SUFFIXES` only matches `*.min.js`-style
names, not `application-<hash>.js` fixture blobs.

## Constraints

- No regression on real minified-adjacent code (vendored libs with real
  symbols, e.g. jquery-4.0.0.slim.js — already excluded by name today
  and must stay excluded; the question is only what ELSE gets caught).
- Discovery-time decision (never enter tags/refs/ranks/MAP), not a
  render-time filter — ranks must never see these nodes.
- Deterministic, stdlib-only, no LLM. Shared constants with discovery.

## Candidate mechanisms (pick one at build time)

1. **Fixture-dir exclusion**: skip subtrees named `fixtures`,
   `__fixtures__`, `testdata` (Rails/Django/Go convention) at discovery.
   Cheap, name-based, zero content sniffing. Risk: real source living
   under such dirs (rare; document).
2. **Content sniffing**: files whose first N lines exceed mean line
   length X with near-zero newlines (minified/gzip blobs) are skipped.
   Catches hash-named blobs mechanism 1 misses. Risk: generated-but-real
   files (lockfiles are already out via extension; check `.d.ts`
   bundles, protobuf outputs).
3. **Hash-name pattern**: `<name>-<hexhash>.js/css` (Rails asset
   fingerprinting, webpack contenthash). Narrow, precise, Rails-shaped.

Recommendation: 1 + 3 (both name-based, no content heuristics), with 2
only if measured MAP-head pollution persists after.

## Acceptance (red-first)

- Fixture: Rails-style `fixtures/public/gzip/application-<hash>.js`
  with minified content + a normal `app.js`; scan must tag the latter,
  zero tags from the former.
- Full suite green, especially language-matrix + discoverability tests.
- Live check: Rails MAP head contains no single-char defs from fixture
  paths; VW/Go MAP bytes unchanged (byte-compare pre/post on canonical
  DBs at fixed budget).

## Non-goals

- Recall for code genuinely living in fixture dirs (documented miss).
- Rewriting `_MINIFIED_SUFFIXES` semantics (additive only).
