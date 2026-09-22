# Proposal for discussion — #45 adaptive escalation + vector embeddings

Two deferred ideas, one shared tension. Both cross the project's founding
line (ROADMAP mission): *deterministic tooling only, no model calls inside
tricorder, built to guard context for 16GB-VRAM home users.* This doc is the
discussion artifact — short on implementation, heavy on the trade-offs and
the one conflict they share.

---

## The shared problem

Today the escalation ladder is **manual**: the agent decides
detect → symbols → detail → query → tier-1/map. `#45` automates *which rung*.
Embeddings change *how a rung matches text*. But they share a root question:

> How much of the actor's judgment do we hand to tricorder, and how much do
> we keep in the agent?

And they share a hard constraint: **any inference on the user's own GPU
steals VRAM from the model that is doing the work** — the exact resource
tricorder exists to protect. That constraint shapes every option below.

---

## Part 1 — #45: adaptive escalation ladder

**What it is today**: `detect` (locate name) → `symbols` (shape) → `detail`
(body + callers/callees) → `query` (graph traversal) → map (last resort). The
agent walks the rungs. `tier_hint` already signals "you stopped too early"
when budget truncated a scan. Nothing picks the rung for you.

**Three ways to spend the idea:**

### Option A — No ladder signal; caller-carrying (status quo, ~zero cost)
Keep the agent responsible for escalation. Add *feedback* only: when
`detect`/`symbols` returns empty even after the fuzzy rescue, return an
explicit signal ("no def found; try `query`/`detail` or widen the search")
instead of a bare empty list. Semi-`symbol_not_found`-style hinting, done.

- Cost: near zero. Fits "the map navigates, the file is truth."
- Ceiling: agent still burns tokens deciding; no real automation.

### Option B — Deterministic auto-escalation via cheap signals (recommended)
Pick the rung by *measurable*, no-model inputs:
- result cardinality (0 hits → escalate to next rung),
- `tier_hint` already present (budget-truncated map → say so loudly),
- fuzzy-rescue fired (matches are orthographic, flag "verify in source"),
- def-vs-ref ratio and file proximity (a `ref` with no local `def` → nudge `query`).

No LLM decides. A fixed decision table in the server, reusing the exact
signals already computed. Return `escalation: {next_rung, reason, evidence}`
on the response so downstream (agent, judge) sees *why*.

This is not full belt-and-braces automation — it stops the cheapest failure
mode (dead-end lookup that silently returns nothing) and never guesses
*content*. It is `deterministic` in the mission's sense.

### Option C — Model-driven rung selection
Let the fronting model (the agent) be told the rung cost/benefit and choose.
That is exactly today's status quo made explicit, just better-documented.
Not a new feature.

**Recommendation: B**, scoped to *"escalate on empty/fuzzy/budget-truncated,
never on content."* C is prose; A is already there.

---

## Part 2 — Vector embeddings

**What exists today**: `detect`/`symbols` do deterministic matching:
exact → substring → regex → orthographic-variant fuzzy rescue (`_query_variants`,
flagged `quality: "fuzzy"`) → **content fallback** (tier 4, added 2026-09-21):
when every name tier comes back empty, `detect` ranks definitions by how
many distinct query concepts their own evidence covers (most covered
first), breaking coverage ties with IDF-weighted token overlap —
synonym-canonicalized, plural/abbreviation-aware — over the def name (3x),
its own source span (1x), and capped caller lines (1x). Bounded one-level
callee spans (0.5x, capped at 4, same-file then cross-file) corroborate via
score only: they never count toward coverage, so a hub cannot win on its
callees' vocabulary. Candidates must cover at least half the query's
concepts with their own evidence and score >= 3, flagged
`quality: "content"`. This is Option A below, shipped: it answers concept
queries ("the thing that serializes the cache") whenever the query's words
appear in docstrings, bodies, call sites, or one hop into callees. No
embeddings, no model calls, no vector store. ROADMAP lists *semantic/vector
code search* (embeddings) as a **non-goal**; deterministic natural-language
→ symbol mapping is no longer one.

**What embeddings would buy**: an agent that types a *concept*
("the thing that serializes the cache") instead of an exact identifier lands
nearby symbols as candidates. That is real value — it is also the thing that
crosses the mission line hardest.

**Three ways to spend the idea:**

### Option A — Deterministic token/text similarity, no ML (recommended as the honest ceiling)
Improve the existing fuzzy rescue deterministically: identifier
tokenization/split-camelCase, subsequence/damerau-levenshtein distance,
a tiny synonym map for common verbs (get/fetch/load, set/store/write), and
**per-file TF-IDF over identifier tokens** so a *name* query still ranks
symbols by *where* they live. All stdlib, all reproducible, no GPU, no model.

- Honors the mission exactly.
- Real ceiling: no semantics. "the thing that serializes" still misses
  `pack`/`dump` if no synonym bridges it.

*Status 2026-09-21: shipped as the tier-4 content fallback
(`Tricorder._content_search_tags`): coverage-first ranking (most distinct
query concepts covered by the definition's own evidence wins; IDF-weighted
score breaks ties) over def name (3x) / own source span (1x) / caller lines
(1x); bounded one-level callee spans (0.5x, capped at 4, same-file then
cross-file) add score only, never coverage. Token pipeline: lowercase,
stopword strip (query side), synonym canonicalization,
inflection-insensitive plurals, small abbreviation map (`dict`→`dictionary`
and back). Floor: cover ≥ half the query concepts with own evidence and
score ≥ 3. The one piece not taken: per-file TF-IDF re-ranking of* name
*queries — tier 4 only fires after every name tier misses, so name-query
ranking is untouched.*

*Measured ranking reliability (2026-09-21, 4 live-agent pilot queries on the
FastAPI corpus, after the full round: morphology + callee expansion +
coverage-first ordering + Python argument-position refs + callee-coverage
refinement): Q2 exact hit #1; Q4 description hit #1; Q1 description hit #2;
Q3 description hit #20. Earlier the same queries scored Q1 #4 and Q3
outside the top 10.
What each fix contributed, measured: synonym/inflection canonicalization
(`dependant`→`depend`) and abbreviation folding (`dictionary`→`dict`) closed
pure vocabulary gaps; bounded one-level callee evidence (same file, then
cross-file, capped at 4 callees, 0.5x weight) recovered concepts set in
helper functions — Q3's "tags"/"summary" live in `get_openapi_operation_metadata`
and friends, not in `get_openapi_path` itself; coverage-first ordering
(-matched, -score) stopped generic `api`/`route` name hits (3x each) from
outranking the candidate covering the most query concepts. A final
refinement, red-tested: callee evidence adds score only, never coverage —
a hub calling four helpers was clearing the floor on their bodies'
vocabulary, so coverage now counts only the definition's own evidence
(name/own span/caller lines). The remaining gaps are the deterministic
ceiling, not weighting bugs: Q1's #1 is the target's own callee
(`contextmanager_in_threadpool`), genuinely the closest relative; Q3's
vocabulary (route/path/operation/api/params/responses/tags/summary) is
shared across dozens of route-related definitions whose own spans
legitimately cover 12–13 of the 15 query concepts — no deterministic
weighting separates them without query-specific hacks.*

*Tagger gap found in the same pass (Q2): the default handler registration
`self.exception_handlers.setdefault(HTTPException, http_exception_handler)`
was invisible because the Python tags query captured only call targets, not
bare identifiers in call-argument position. Extended
`queries/tree-sitter-language-pack/python-tags.scm` (2026-09-21) to capture
positional and keyword-value argument identifiers as refs — narrow on
purpose (attribute values and splats stay untagged) so ref volume and
caller noise stay bounded. Red-tested: argument-position identifiers now
appear as ref tags, so registration-by-argument sites are findable via
`detect`/`symbols`/`detail` callers. Cache note: the per-file tags cache is
keyed by file fingerprint only, so the new capture would have been masked
by stale entries — caught by a red test, fixed per the project's own rule
("bump on ANY capture change") by raising `EXTRACTOR_VERSION` 2→3 in
`database.py`, which re-keys the cache directory and re-stamps DBs.*

### Option B — Local embedder (crosses the line, cheaper than it sounds)
Run a small self-hosted embedding model (e.g. sentence-transformers mini /
fastembed) once at scan time, store vectors in sqlite (tricorder already is
sqlite). Query-time cosine sim replaces/edges the fuzzy rescue.

- The **only** option that genuinely answers concept queries.
- Costs: a new ML dependency; scan-time CPU/VRAM spike; the 16GB-VRAM user
  temporarily loans VRAM from their inference model; vectors bloat the DB
  (x embeddings × ~384–3840 floats); embedding drift between model updates.
- `deterministic tooling only` is dead; it becomes *mostly-deterministic*.

### Option C — Remote embed API (the one that does NOT consume local VRAM)
Ship identifier → embed to a hosted API at index time, store vectors locally.
Keeps the model off the user's GPU (zero VRAM steal) at the price of: an
account/key, a network dependency, per-vector cost, and **privacy — your
identifiers leave the box.** For a tool whose pitch is *local, private,
deterministic*, this is the worst fit of the three unless the user already
self-hosts an emb server.

---

## The shared decision

Both ideas converge on one fork:

- **Stay deterministic** (Part 1 → B, Part 2 → A). Cheapest, mission-true,
  real token savings on the dead-end-lookup failure mode, no new deps, no
  VRAM hit, no privacy change. What you *don't* get: true concept search.
- **Go semantic** (Part 2 → B/C). You buy concept search. You pay with the
  mission line, a dependency, and either VRAM (B) or privacy/cost/network (C).
  Note B and C are mutually exclusive on the VRAM axis.

There is no free lunch between "concept search" and "deterministic, local,
no-VRAM." The proposal is: **do Part 1 → B and Part 2 → A now** (both keep
the ladder and the pointer deterministic, both are small diffs), and treat
Part 2 → B as a separately-sponsored experiment with its own VRAM measurement
benchmark before it touches main.

**Open questions for the discussion:**
1. Is "concept search" a must-have, or is narrowing the gap with better
   deterministic fuzzy (Part 2 → A) enough? 
2. If embeddings must happen, does the VRAM cost (Option B) or the privacy/
   network cost (Option C) violate the mission worse?
3. For #45, is `escalation:{next_rung,reason,evidence}` on empty/fuzzy/
   truncated the right signal for the agent and the judge, or do you want the
   server to actually *re-run* the next rung (server-side auto-escalation)?