# Tiering and retrieval — spending tokens on purpose

Principle: retrieve, don't rescan. A fresh DB answers everything below;
a full re-scan at query time is never the right move.

## Tiers (unchanged on dev-db)

`--tier` is a CLI/MCP-level multiplier on `context_lines`
(`tricorder.py`: `context_lines = int(args.tier) * args.context_lines`;
server: `context_lines if tier > 0 else 0`):

- **tier 0** — definition lines only. Cheapest complete picture.
- **tier 1** — definitions + ±N source lines each (`--context-lines`,
  default 3). Zeroing in.

`render.py` branches on `context_lines == 0` ("T0 mode"): def lines
render directly, no file reads. Tier >0 pays one read per shown tag.
The dev-db work did not change this mechanism — it changed what feeds
it (DB-backed tags instead of in-RAM dicts).

## Escalation ladder (cheapest first)

detect (locate name) → symbols (shape: type, range, signature) →
detail (body + callers + callees) → query (graph traversal) →
tier-1 / full map (last resort). Each step costs more than the last;
stop at the first that answers. Before asserting or editing anything
found this way, open the exact file lines — the map navigates, the
file is truth.

## Session recipe (mapped repo, CLI)

1. `tricorder <path> --db-path <db> --tier 0` — orient (defs only).
2. `--pre-index NAME` or `--probe-digest` — locate, don't browse.
3. `--tier 1` on the files that matter — read context.
4. Open the real files. Edit. Re-run: only dirty files reparse.

## Slash commands (Hermes plugin)

`/tricorder root|scan|status|help`. `scan` shells the CLI with
`--db-path` pointed at the canonical in-repo DB — so a slash scan
populates the same sqlite turn-0, MCP, and `chunk_resume.py` read.
Default cap 1000 files (`max_files` config); full coverage still goes
through `chunk_resume.py`.

- `tricorder <path> --db-path <db> --tier 0` — definitions fast path.
- `--pre-index SYMBOL` — narrow giant trees before walking.
- `--probe-digest` — cheap language/file tally + navigation hint, no
  map. This is what turn-0 injection uses on unmapped repos.
- `--stats-only [MAP]` / `--signature-only` — inspect budget and
  freshness without mapping.
- `--dry-run` — token/budget estimate for a planned map.

## MCP + turn-0 plugin — TBD (not ported)

`tricorder_server.py` (tools: scan, detect, symbols, detail, query)
and the Hermes/DSH turn-0 injectors (`tricorder_inject.py`,
`tricorder_client.py`, `plugins/`) exist in tree but are **not
revalidated on this branch**. Intended flow once ported: fresh session
with the repo as root → turn-0 injects the one-line DB digest (or the
cheap probe digest marked not-pre-mapped) → agent navigates via MCP
tools against the DB → works on real files. No usage docs for this
section until the port lands and is verified live.
