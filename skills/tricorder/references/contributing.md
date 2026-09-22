# Developing / Maintaining Tricorder (contributor notes)

When editing the tricorder repo itself (not just calling it), the load-bearing invariants and recipes below hold. Full detail in `references/tricorder_dev_notes.md`.

## Write-invariant — never write into a scanned repo
Every in-process write routes through `utils.safe_write(path, text, *, allow_escape=False)`. Default: target must resolve inside `get_cache_root()` (== `<tricorder workspace>/.tricorder`, overridable via `TRICORDER_CACHE_HOME`) or it raises `ValueError` **loud** (not swallowed). `--output` is the only sanctioned escape (`allow_escape=True`); it still wraps the write in `except OSError` + stdout fallback so the map is never lost. I/O errors raise `OSError` so best-effort caches swallow only disk failures. Wired sites: `utils.py` budget cache, `ctags_probe.py` tags meta, `tricorder_server.py` output, `tricorder.py --output`. The plugin (`plugins/tricorder/__init__.py`) is intentionally out-of-process (shells to CLI in its own venv) and is NOT reached by `safe_write` — by design.

## TC-threat-model audit (cheap coverage check after any change)
Tickets TC-001..010 encode the security model. Grep the tests dir for `TC-0` (`rg "TC-0[0-9]" tests/ -n`) to confirm no ticket regressed to zero coverage. Last full audit: TC-001..008 + TC-010 covered; TC-009 (dep pinning) was the last gap → `tests/test_tc009_dep_pinning.py` asserts every `requirements.txt` line is `==`-pinned. Re-run the grep whenever you add/remove a behavior.

## Verify recipes (run from repo root — tests insert `.` into sys.path)
- Full suite: `python -m pytest tests/ -v` (baseline 185 passed, 19 subtests).
- `--output` escape hatch on native Windows `python.exe`: use a real Windows absolute path (`C:/tmp/check.json`). Native python does NOT translate MSYS `/tmp` — it becomes `D:\tmp\...` relative to cwd. Expect exit 0 + file written.
- Unwritable cache root: `TRICORDER_CACHE_HOME=/tmp/nw/blocker/.tricorder python tricorder.py scan .` → must still emit a map (exit 0), not crash.
- README keeps a "Running Tests (Agent Instructions)" section; keep it in sync when adding tests.
- Commit/push: Gitea `hermes-agent` identity, token inline in origin URL; push origin then github. Never use `~/.gitea_pat` (see gitea-workflow skill).
