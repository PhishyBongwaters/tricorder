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
flagged `quality: "fuzzy"`). No embeddings, no model calls, no vector store.
ROADMAP explicitly lists *natural-language → symbol mapping* and *semantic/
vector code search* as **non-goals**.

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