# Eval analysis tools (promoted from scratch 2026-09-25)

Read-only helpers behind TRUE-TALLY.md and the harness-truth method.
Nothing here writes to DBs or edits eval data. Run from repo root with
the repo `.venv` (`sys.path.insert(0, '.')` where needed).

## Harness truth (opencode.db session store)

- `ocdb.py` — list general-agent subagent sessions with usage
  (input/output/cache_read) + titles. Edit the query for other slices.
- `ocmsg.py` — inspect one assistant message: token payload, part types
  (text vs tool), tool-call detail.
- `ocmap.py` — per-session table: model, title, input/output/cache_read,
  harness tool-call count. Basis of the session→leg map.
- `occtx.py` — fresh-input vs cache-re-read vs output split + peak
  context per call, for the 16 mapped v13 sessions (edit `legs` dict
  for other sessions).
- `octools.py` — verify every tool part in a session carries returned
  content (completeness of the audit trail).
- `ocover.py` — price first-ground-truth-hit vs session total
  (over-verification, exactly measured). Session ID hardcoded; edit it.

## Artifact audit (artifact era, kept for provenance)

- `audit_legs.py` — step_*.txt vs transcript-row completeness per v13 leg.
- `meter` lives with the rounds (`v13/meter_leg.py`).

## One-off investigations (trail, not API)

- `backfill_ranks.py <db>` — the op used for Go/Rails/VW/Vue/Elixir/Swift
  backfills (additive only). `verify_backfill.py`, `dbsize.py` alongside.
- `db_inventory.py` — all canonical DBs: def counts, ranks presence.
- `go_counts.py`, `go_check.py`, `go_refs.py`, `go_scan_floor.py`,
  `goranks.py` — Go MAP-timeout diagnosis trail.
- `qinv.py`, `gtinv.py` — question/ground-truth inventory for the book.
- `swift_gt.py` — abandoned (full in-memory Swift parse; timed out).
  Kept as a warning: scope Swift via DB, never `use_db=False`.
- `vw_comp.py` — Vaultwarden composition (tagged core vs SQL shell).
- `dbg_heal.py` — warm-serve skip diagnosis scratch.
