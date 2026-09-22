"""Round 8 regression tests.

1. _canonical_db_for must not cache "no DB": a canonical DB created after
   the server starts must be found on the next lookup.
2. _get_tricorder must rebuild its cached instance when the resolved DB
   path changes (preserving the warm instance otherwise).
3. read_only_connect must handle DB paths containing '#' or '?'.
4. --db-path pointing at a directory must produce a clean parser error on
   the scan path (not a sqlite3 traceback).
5. --no-db + --db-path together must be rejected by the parser.
"""

import os
import subprocess
import sys

import pytest

from database import DBStore
from utils import read_only_connect


def _seed_db(path):
    db = DBStore(path)
    try:
        db.set_meta("/somewhere", "sig")
        db.set_file_state("a.py", 10, 1234567890)
        db.insert_tags([("/somewhere/a.py", "a.py", 1, "foo", "def")])
        db.commit()
    finally:
        db.close()


# --- 1+2: server cache staleness -------------------------------------------

def test_canonical_db_for_picks_up_late_created_db(tmp_path, monkeypatch):
    import tricorder_server as srv

    root = tmp_path / "myrepo"
    root.mkdir()
    monkeypatch.setattr(srv, "PRE_SCAN_DB_DIR", tmp_path / "cachedb")

    # First lookup: nothing exists.
    assert srv._canonical_db_for(str(root)) is None

    # Create the canonical DB afterwards (meta root must match).
    db_dir = tmp_path / "cachedb"
    db_dir.mkdir(parents=True, exist_ok=True)
    db_path = db_dir / "myrepo.db"
    db = DBStore(str(db_path))
    try:
        db.set_meta(str(root), "sig")
        db.commit()
    finally:
        db.close()

    # A cached "no DB" would keep returning None here.
    assert srv._canonical_db_for(str(root)) == str(db_path)


def test_get_tricorder_rebuilds_when_db_appears(tmp_path, monkeypatch):
    import tricorder_server as srv

    root = tmp_path / "myrepo2"
    root.mkdir()
    (root / "a.py").write_text("x = 1\n")
    monkeypatch.setattr(srv, "PRE_SCAN_DB_DIR", tmp_path / "cachedb2")
    srv._tricorder_cache.clear()

    first = srv._get_tricorder(str(root))
    assert first._db_path is None  # no DB yet -> in-memory

    db_dir = tmp_path / "cachedb2"
    db_dir.mkdir(parents=True, exist_ok=True)
    db_path = db_dir / "myrepo2.db"
    db = DBStore(str(db_path))
    try:
        db.set_meta(str(root), "sig")
        db.commit()
    finally:
        db.close()

    second = srv._get_tricorder(str(root))
    assert second._db_path == str(db_path)  # stale in-memory instance replaced
    srv._tricorder_cache.clear()


# --- 3: URI-escaped read-only opens ----------------------------------------

# '?' is illegal in Windows file names, so that case only runs on POSIX.
_SPECIAL_DIRS = ["repo#1", "repo 100%"]
if os.name != "nt":
    _SPECIAL_DIRS = _SPECIAL_DIRS + ["repo?x"]

@pytest.mark.parametrize("dirname", _SPECIAL_DIRS)
def test_read_only_connect_special_char_dirs(tmp_path, dirname):
    d = tmp_path / dirname
    d.mkdir()
    db_path = str(d / "idx.db")
    _seed_db(db_path)
    con = read_only_connect(db_path)
    try:
        n = con.execute("SELECT COUNT(*) FROM file_state").fetchone()[0]
    finally:
        con.close()
    assert n == 1


# --- 4+5: CLI parser guards ------------------------------------------------

def _cli(*args):
    return subprocess.run(
        [sys.executable, "tricorder.py", *args],
        cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        capture_output=True, text=True, timeout=120,
    )


def test_db_path_directory_scan_is_clean_parser_error(tmp_path):
    sub = tmp_path / "sub"
    sub.mkdir()
    (tmp_path / "a.py").write_text("x = 1\n")
    p = _cli("--root", str(tmp_path), "--db-path", str(sub))
    assert p.returncode == 2, p.stderr
    assert "--db-path is not a file" in p.stderr
    assert "Traceback" not in p.stderr


def test_no_db_and_db_path_are_mutually_exclusive(tmp_path):
    (tmp_path / "a.py").write_text("x = 1\n")
    p = _cli("--root", str(tmp_path), "--no-db", "--db-path", str(tmp_path / "x.db"))
    assert p.returncode == 2, p.stderr
    assert "not allowed with" in p.stderr
