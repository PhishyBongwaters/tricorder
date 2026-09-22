"""Round 12 review: plugin coverage must not fall back to tags-distinct.

Round 10 fixed the CLI --db-coverage path: a DB without file_state
(pre-Goal-3) has unknowable coverage and is treated as unmapped (house
rule: coverage is COUNT(*) FROM file_state, never distinct tags).
The Hermes plugin (plugins/tricorder/__init__.py) has the same
fallback in TWO places and was missed:

1. _tricorder_db_for() — the "is this repo mapped?" gate falls back to
   COUNT(DISTINCT rel_file) FROM tags, so a pre-Goal-3 DB reports as
   mapped with a wrong file count.
2. _db_coverage_line() — same fallback in the coverage string.

Both must treat a pre-file_state DB as unmapped instead.
"""
import importlib
import sqlite3
import sys
import tempfile
import types
from pathlib import Path

import pytest


def _import_plugin():
    """Import plugins.tricorder with hermes config faked (as in
    test_review_round9), return (module, teardown)."""
    fake_cfg = {'plugins': {'entries': {'tricorder': {}}}}
    sys.modules['hermes_cli.config'] = types.SimpleNamespace(
        load_config=lambda: fake_cfg)
    sys.modules['hermes_constants'] = types.SimpleNamespace(
        get_hermes_home=lambda: Path(tempfile.mkdtemp()))
    plugin = importlib.import_module('plugins.tricorder')
    # The plugin memoizes the CLI lookup; never resolve it in tests.
    plugin._TRICORDER_CLI = "/nonexistent/tricorder"

    def teardown():
        sys.modules.pop('hermes_cli.config', None)
        sys.modules.pop('hermes_constants', None)
        sys.modules.pop('plugins.tricorder', None)
    return plugin, teardown


def _make_pre_goal3_db(root: Path, cache: Path) -> Path:
    """A pre-Goal-3 index DB in the cache root: tags + meta, but NO file_state table."""
    db_dir = cache / "db"
    db_dir.mkdir(parents=True, exist_ok=True)
    db_path = db_dir / (root.name + ".db")
    con = sqlite3.connect(str(db_path))
    con.execute("CREATE TABLE tags(file TEXT, rel_file TEXT, line INTEGER, name TEXT, kind TEXT)")
    con.execute("CREATE TABLE meta(schema_version INTEGER, root TEXT, signature TEXT, extractor_version INTEGER)")
    con.executemany(
        "INSERT INTO tags(file, rel_file, line, name, kind) VALUES (?,?,?,?,?)",
        [(str(root / "a.py"), "a.py", 1, "alpha", "def"),
         (str(root / "b.py"), "b.py", 2, "beta", "def")],
    )
    con.execute(
        "INSERT INTO meta(schema_version, root, signature, extractor_version) VALUES (?,?,?,?)",
        (1, str(root), "deadbeef", 2),
    )
    con.commit()
    con.close()
    return db_path


def test_plugin_db_for_ignores_pre_file_state_db(tmp_path, monkeypatch):
    """_tricorder_db_for must not report a pre-Goal-3 DB as mapped."""
    import utils
    root = tmp_path / "proj"
    root.mkdir()
    cache = tmp_path / "tcache"
    monkeypatch.setattr(utils, "_CACHE_ROOT", None)
    monkeypatch.setenv("TRICORDER_CACHE_HOME", str(cache))
    plugin, teardown = _import_plugin()
    try:
        db_path = _make_pre_goal3_db(root, cache)
        assert db_path.exists()
        # A tags-distinct fallback would return the path ("2 files mapped").
        assert plugin._tricorder_db_for(str(root)) is None
    finally:
        teardown()


def test_plugin_coverage_line_rejects_pre_file_state_db(tmp_path, monkeypatch):
    """_db_coverage_line must not emit a tags-distinct coverage line."""
    import utils
    root = tmp_path / "proj"
    root.mkdir()
    cache = tmp_path / "tcache"
    monkeypatch.setattr(utils, "_CACHE_ROOT", None)
    monkeypatch.setenv("TRICORDER_CACHE_HOME", str(cache))
    plugin, teardown = _import_plugin()
    try:
        db_path = _make_pre_goal3_db(root, cache)
        # The caller falls back to the probe digest on exception; a
        # tags-distinct count here would misreport coverage.
        with pytest.raises(Exception):
            plugin._db_coverage_line(str(db_path), str(root))
    finally:
        teardown()


def test_plugin_db_for_accepts_current_db(tmp_path, monkeypatch):
    """Control: a current-schema DB with file_state still reports mapped.

    The DB lives in the cache root (TRICORDER_CACHE_HOME) — never inside
    the scanned repo."""
    root = tmp_path / "proj"
    root.mkdir()
    cache = tmp_path / "tcache"
    monkeypatch.setenv("TRICORDER_CACHE_HOME", str(cache))
    plugin, teardown = _import_plugin()
    try:
        db_dir = cache / "db"
        db_dir.mkdir(parents=True)
        db_path = db_dir / (root.name + ".db")
        con = sqlite3.connect(str(db_path))
        con.execute("CREATE TABLE tags(file TEXT, rel_file TEXT, line INTEGER, name TEXT, kind TEXT)")
        con.execute("CREATE TABLE file_state(rel_file TEXT PRIMARY KEY, size INTEGER, mtime INTEGER)")
        con.execute("CREATE TABLE meta(schema_version INTEGER, root TEXT, signature TEXT, extractor_version INTEGER)")
        con.execute("INSERT INTO file_state(rel_file, size, mtime) VALUES (?,?,?)", ("a.py", 10, 123))
        con.execute(
            "INSERT INTO meta(schema_version, root, signature, extractor_version) VALUES (?,?,?,?)",
            (1, str(root), "deadbeef", 2),
        )
        con.commit()
        con.close()
        assert plugin._tricorder_db_for(str(root)) == str(db_path)
        line = plugin._db_coverage_line(str(db_path), str(root))
        assert "mapped: 1 files" in line
    finally:
        teardown()


# --- rescan of a fully-mapped repo must render from the index ---------------
# drop_mapped_files() empties the discovered list when every file is already
# mapped; the CLI/MCP then rendered an empty map with a misleading "No files
# found" warning — and never re-parsed modified files (dropped before the
# DB dirty-diff could see them). The fix: when the drop yields empty from a
# non-empty discovery, fall back to the capped list; the DB-backed dirty
# diff skips clean files (zero re-parses) and re-parses dirty ones.
import subprocess as _sp

_CLI = str(Path(__file__).resolve().parent.parent / "tricorder.py")
_PYBIN = sys.executable


def _cli_run(root, *args):
    return _sp.run([_PYBIN, _CLI, "--root", str(root), "--map-tokens",
                    "100000", "--quiet", *args],
                   capture_output=True, text=True, timeout=180)


def _write(root: Path, name: str, body: str):
    (root / name).write_text(body, encoding="utf-8")


def test_rescan_of_fully_mapped_repo_renders_map(tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    _write(root, "a.py", "def alpha():\n    pass\n")
    _write(root, "b.py", "def beta():\n    pass\n")
    assert _cli_run(root, "--init").returncode == 0
    assert _cli_run(root).returncode == 0  # first scan populates index
    r = _cli_run(root)  # rescan: everything already mapped
    assert r.returncode == 0, r.stderr[-500:]
    assert "No files found" not in r.stderr, \
        "rescan of a mapped repo must not claim no files found"
    assert "def alpha" in r.stdout
    assert "def beta" in r.stdout


def test_rescan_reparses_modified_file(tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    _write(root, "a.py", "def alpha():\n    pass\n")
    assert _cli_run(root, "--init").returncode == 0
    assert _cli_run(root).returncode == 0
    _write(root, "a.py", "def alpha():\n    pass\n\ndef gamma_new():\n    pass\n")
    r = _cli_run(root)
    assert r.returncode == 0, r.stderr[-500:]
    assert "def gamma_new" in r.stdout, \
        "modified file must be re-parsed on rescan, not dropped as mapped"


def test_fixed_cap_rerun_renders_indexed_slice(tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    for i in range(4):
        _write(root, f"f{i}.py", f"def f{i}():\n    return {i}\n")
    assert _cli_run(root, "--init").returncode == 0
    assert _cli_run(root, "--max-files", "2").returncode == 0
    r = _cli_run(root, "--max-files", "2")
    assert r.returncode == 0, r.stderr[-500:]
    assert "No files found" not in r.stderr
    # Fixed-cap rerun adds zero re-parses but still renders the indexed slice.
    assert "def f0" in r.stdout
    assert "def f1" in r.stdout


def test_single_tag_map_renders(tmp_path):
    """A repo whose map holds exactly one tag must still render.

    The token-budget binary search probed num_tags=0 first and gave up,
    so single-def repos always got 'No map content generated'."""
    root = tmp_path / "proj"
    root.mkdir()
    _write(root, "a.py", "def solo():\n    pass\n")
    r = _cli_run(root)
    assert r.returncode == 0, r.stderr[-500:]
    assert "def solo" in r.stdout


def test_rescan_after_edit_serves_fresh_map(tmp_path):
    """The persistent render cache must not serve a stale map after an edit.

    The cache key carried no content fingerprint, so a rescan after editing
    a file returned the previous render (or a cached empty one)."""
    root = tmp_path / "proj"
    root.mkdir()
    _write(root, "a.py", "def alpha():\n    pass\n")
    _write(root, "b.py", "def beta_old():\n    pass\n")
    assert _cli_run(root, "--init").returncode == 0
    assert _cli_run(root).returncode == 0
    r1 = _cli_run(root)
    assert "def beta_old" in r1.stdout
    _write(root, "b.py", "def beta_new():\n    pass\n")
    r2 = _cli_run(root)
    assert r2.returncode == 0, r2.stderr[-500:]
    assert "def beta_new" in r2.stdout, "rescan must reflect the edit"
    assert "def beta_old" not in r2.stdout, "rescan must not serve the stale map"


def test_rising_cap_resume_after_delete(tmp_path):
    """Rising-cap resume must survive a deleted file: no crash, and the
    new slice still renders."""
    root = tmp_path / "proj"
    root.mkdir()
    for i in range(4):
        _write(root, f"f{i}.py", f"def f{i}():\n    pass\n")
    assert _cli_run(root, "--init").returncode == 0
    assert _cli_run(root, "--max-files", "2").returncode == 0
    (root / "f0.py").unlink()
    r = _cli_run(root, "--max-files", "4")
    assert r.returncode == 0, r.stderr[-500:]
    assert "Traceback" not in r.stderr
    assert "def f2" in r.stdout
    assert "def f3" in r.stdout
