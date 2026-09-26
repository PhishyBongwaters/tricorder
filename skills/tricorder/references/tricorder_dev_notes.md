# Tricorder Contributor / Maintenance Notes

## The write-invariant (never write to scanned repos)
All in-process writes route through `utils.safe_write(path, text, *, allow_escape=False)`.
- Default: target must resolve inside `get_cache_root()` (== the user-level cache root, overridable via `TRICORDER_CACHE_HOME`). A target outside raises `ValueError` — loud, not swallowed.
- `--output` passes `allow_escape=True` (sanctioned user path); still wrapped in `except OSError` with stdout fallback so the map is never lost.
- I/O errors raise `OSError` so best-effort caches (budget/tags) swallow only disk failures via `except OSError: pass`; escapes raise `ValueError` (NOT swallowed).
- Wired sites: `utils.py` budget cache, `ctags_probe.py` tags meta, `tricorder_server.py` output (`get_cache_root()/"output"`), `tricorder.py --output`.
- Plugin (`plugins/tricorder/__init__.py`) is INTENTIONALLY out-of-process (shells to CLI in its own venv) → `safe_write` not reachable there; writes to `hermes_home/tricorder`, outside scanned repos, fine as-is.
- The `--output` guard lives inside `tricorder.py`'s existing `except OSError` block; import `safe_write` from `utils` there too (it is needed — a missing import surfaces as `name 'safe_write' is not defined` at scan time).

## TC-threat-model audit (coverage check)
Tickets: TC-001 untrusted markers, TC-002 resource envelope, TC-003 cache isolation, TC-004 parser timeout, TC-005 trust metadata, TC-006 path containment, TC-007 max_files clamp, TC-008 output containment, TC-009 dep pinning, TC-010 parser fuzz.
Grep the tests dir after any change: `rg "TC-0[0-9]" tests/ -n` (or search_files pattern `TC-00[0-9]`).
As of last audit: TC-001..008 + TC-010 covered. TC-009 was the last gap → `tests/test_tc009_dep_pinning.py` asserts every `requirements.txt` line is `==`-pinned (single loop, no framework). Re-run the grep to confirm no ticket regressed to zero coverage.

## Test / verify recipes
- Run from repo root (tests insert `.` into sys.path): `python -m pytest tests/ -v`.
- Targeted smoke: `python -m pytest tests/test_safe_write.py tests/test_regression_phase1.py tests/test_mcp.py tests/test_cli_autodiscovery.py -q` (62 passed).
- Verify `--output` escape hatch (Windows native python.exe): use a real Windows absolute path, e.g. `python tricorder.py scan . --output C:/tmp/check.json`. Native `python.exe` does NOT translate MSYS `/tmp` (it becomes `D:\tmp\...` relative to cwd); an MSYS `/tmp/...` path silently writes under the repo's drive. Expect exit 0 + file written.
- Verify graceful degradation on unwritable cache root: `TRICORDER_CACHE_HOME=/tmp/nw/blocker/.tricorder python tricorder.py scan .` → must still produce a map (exit 0), not crash.
- Full-suite green baseline: 185 passed, 19 subtests passed.

## README agent instructions
README has a "Running Tests (Agent Instructions)" section: run from root, targeted + full-suite pytest, caveat that pytest must run from root. Keep that section in sync when adding tests. Security Model TC-008 row documents the `safe_write()` structural guard.

## Commit / push
Gitea workflow (gitea-workflow skill): identity `hermes-agent`, token inline in origin URL (`http://hermes-agent:TOKEN@192.168.2.81:3001/projects/tricorder.git`). Push origin then github. NEVER use `C:\Users\macdo\.gitea_pat`. Concurrent autonomous sessions may have modified files — review before including in a commit.
