"""No-repo-writes: nothing tricorder does may write state into the scanned repo.

User requirement: state lives in the tricorder workspace cache root
(TRICORDER_CACHE_HOME or <workspace>/.tricorder/), never in the scanned
repo. `tricorder --init` used to create <repo>/.tricorder/db/<name>.db
inside the target; it must create the canonical DB in the cache root.
"""
import subprocess as _sp
import sys
from pathlib import Path

_CLI = str(Path(__file__).resolve().parent.parent / "tricorder.py")
_PYBIN = sys.executable


def _fresh_cache(monkeypatch, cache):
    """Point the cache root at tmp dir, bypassing utils' _CACHE_ROOT memo."""
    import utils
    monkeypatch.setattr(utils, "_CACHE_ROOT", None)
    monkeypatch.setenv("TRICORDER_CACHE_HOME", str(cache))


def _cli_run(root, *args):
    return _sp.run([_PYBIN, _CLI, "--root", str(root), "--map-tokens",
                    "100000", "--quiet", *args],
                   capture_output=True, text=True, timeout=180)


def test_init_writes_nothing_into_scanned_repo(tmp_path, monkeypatch):
    root = tmp_path / "proj"
    root.mkdir()
    (root / "a.py").write_text("def alpha():\n    pass\n", encoding="utf-8")
    cache = tmp_path / "tcache"
    _fresh_cache(monkeypatch, cache)

    r = _cli_run(root, "--init")
    assert r.returncode == 0, r.stderr[-500:]
    assert not (root / ".tricorder").exists(), \
        "--init must not create .tricorder inside the scanned repo"
    db = cache / "db" / "proj.db"
    assert db.exists(), \
        f"--init must create the canonical DB in the cache root, stdout={r.stdout!r}"


def test_init_then_scan_resumes_from_cache_db(tmp_path, monkeypatch):
    """The relocated --init DB must still serve rescan resumption."""
    root = tmp_path / "proj"
    root.mkdir()
    (root / "a.py").write_text("def alpha():\n    pass\n", encoding="utf-8")
    cache = tmp_path / "tcache"
    _fresh_cache(monkeypatch, cache)

    assert _cli_run(root, "--init").returncode == 0
    assert _cli_run(root).returncode == 0  # first scan populates index
    r = _cli_run(root)  # rescan: everything already mapped
    assert r.returncode == 0, r.stderr[-500:]
    assert "def alpha" in r.stdout


def test_init_rejects_same_name_cache_db_owned_by_another_root(tmp_path, monkeypatch):
    """A shared cache must not let one same-named repo take another's DB."""
    root_a = tmp_path / "one" / "proj"
    root_b = tmp_path / "two" / "proj"
    root_a.mkdir(parents=True)
    root_b.mkdir(parents=True)
    cache = tmp_path / "tcache"
    _fresh_cache(monkeypatch, cache)

    first = _cli_run(root_a, "--init")
    assert first.returncode == 0, first.stderr[-500:]

    second = _cli_run(root_b, "--init")
    assert second.returncode != 0
    assert "already owned" in second.stderr

    import sqlite3
    db = cache / "db" / "proj.db"
    assert db.exists()
    con = sqlite3.connect(str(db))
    try:
        stored_root = con.execute("SELECT root FROM meta").fetchone()[0]
    finally:
        con.close()
    assert stored_root == str(root_a.resolve())
