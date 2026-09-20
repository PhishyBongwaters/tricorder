"""Round 7 regression tests: drop_mapped_files must open the DB read-only.

Round 6 made CLI --diff "truly read-only", but the --diff flow calls
drop_mapped_files() before constructing the read-only Tricorder, and that
helper opened DBStore read-write (DDL + migration + commit at init) --
attempting a write against a read-only checkout on every diff.
"""

import os
import sqlite3

import pytest

import database
from database import DBStore, drop_mapped_files


def _seed_db(tmp_path):
    root = tmp_path / "repo"
    (root / "pkg").mkdir(parents=True)
    f = root / "pkg" / "a.py"
    f.write_text("def hello():\n    return 1\n")
    db_path = str(tmp_path / "idx.db")
    db = DBStore(db_path)
    try:
        db.set_file_state("pkg/a.py", 10, 1234567890)
        db.insert_tags([("pkg/a.py", "pkg/a.py", 1, "hello", "def")])
        db.commit()
    finally:
        db.close()
    return root, db_path


def test_drop_mapped_files_uses_read_only_connect(tmp_path, monkeypatch):
    """drop_mapped_files must open the DB through read_only_connect so a
    read-only checkout is never touched with DDL/migration/commit."""
    root, db_path = _seed_db(tmp_path)
    root = os.path.realpath(root)  # drop_mapped_files compares against realpath

    calls = []
    real_ro = database.read_only_connect

    def spy(path):
        calls.append(path)
        return real_ro(path)

    monkeypatch.setattr(database, "read_only_connect", spy)

    rw_calls = []
    real_connect = sqlite3.connect

    def rw_spy(*a, **k):
        rw_calls.append((a, k))
        return real_connect(*a, **k)

    monkeypatch.setattr(sqlite3, "connect", rw_spy)

    files = drop_mapped_files([os.path.join(root, "pkg", "a.py")],
                              root, db_path)

    # The mapped file is dropped; only the read-only opener was used.
    assert files == []
    assert calls == [db_path]
    rw_opens = [a for a, k in rw_calls
                if not (k.get("uri") and "mode=ro" in str(a[0]))]
    assert rw_opens == [], f"read-write connects attempted: {rw_opens}"


def test_drop_mapped_files_on_unwritable_db_returns_files(tmp_path, monkeypatch):
    """Against an unwritable DB the read-only open succeeds, so the mapped
    file is actually dropped instead of silently skipped."""
    root, db_path = _seed_db(tmp_path)
    root = os.path.realpath(root)  # drop_mapped_files compares against realpath
    os.chmod(db_path, 0o444)
    try:
        files = drop_mapped_files([os.path.join(root, "pkg", "a.py")],
                                  root, db_path)
    finally:
        os.chmod(db_path, 0o644)
    assert files == []
