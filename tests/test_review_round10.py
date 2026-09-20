"""Round 10: WAL-checkpoint visibility for immutable readers, sqlite handle
leaks in the MCP server, clean KeyboardInterrupt handling in the CLI."""
import asyncio
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

import pytest

from core import Tricorder
from database import DBStore
from utils import read_only_connect
import tricorder_server as srv

_QH = {'info': lambda *a: None, 'warning': lambda *a: None,
       'error': lambda *a: None}


def _repo(n=2):
    d = Path(tempfile.mkdtemp())
    for i in range(n):
        (d / f"f{i}.py").write_text(f"def func{i}():\n    return {i}\n")
    return d


def _scan(root, db_path, files):
    t = Tricorder(root=str(root), db_path=str(db_path),
                  output_handler_funcs=_QH)
    # Deliberately NOT closed: the CLI never closes its Tricorder, and the
    # MCP server holds cached instances open across calls.
    return t.get_ranked_tags([], [str(f) for f in files])


def test_fresh_scan_visible_to_immutable_reader():
    """A completed first scan must be visible to frozen readers.

    --diff / --db-coverage / tricorder_diff open the DB with immutable=1
    (they must never see uncheckpointed WAL rows per read_only_connect's
    contract). The first scan into a fresh DB never checkpointed, so a
    subsequent --diff reported 'No scan index found' — every file as added.
    """
    d = _repo(2)
    p = str(d / "idx.db")
    _scan(d, p, [d / "f0.py", d / "f1.py"])
    con = read_only_connect(p)
    try:
        rows = con.execute("SELECT COUNT(*) FROM file_state").fetchone()[0]
    finally:
        con.close()
    assert rows == 2


def test_incremental_scan_visible_to_immutable_reader():
    """Same visibility guarantee for the incremental (dirty-file) path."""
    d = _repo(2)
    p = str(d / "idx.db")
    files = [d / "f0.py", d / "f1.py"]
    _scan(d, p, files)
    (d / "f1.py").write_text("def func1():\n    return 'changed'\n")
    os.utime(d / "f1.py", (2000000000, 2000000000))
    _scan(d, p, files)
    con = read_only_connect(p)
    try:
        mtime = con.execute(
            "SELECT mtime FROM file_state WHERE rel_file='f1.py'").fetchone()[0]
    finally:
        con.close()
    assert mtime == 2000000000


def test_diff_sees_incremental_additions():
    """No phantom 'added' files: a file indexed by an incremental scan must
    not reappear as added to a later read-only diff."""
    d = _repo(1)
    p = str(d / "idx.db")
    _scan(d, p, [d / "f0.py"])
    (d / "f1.py").write_text("def func1():\n    return 1\n")
    _scan(d, p, [d / "f0.py", d / "f1.py"])
    reader = Tricorder(root=str(d), db_path=p, db_read_only=True,
                       output_handler_funcs=_QH)
    try:
        diff = reader.diff_against_index()
    finally:
        reader.close() if hasattr(reader, "close") else None
    assert diff["indexed"] is True
    assert "f1.py" not in diff["added"]
    assert diff["added"] == []


def test_get_tricorder_lru_eviction_closes():
    """Evicted cached instances must not leak their sqlite handles."""
    srv._tricorder_cache.clear()
    r1, r2 = Path(tempfile.mkdtemp()), Path(tempfile.mkdtemp())
    try:
        import tricorder_server as s2
        old_max = s2._TRICORDER_CACHE_MAX
        s2._TRICORDER_CACHE_MAX = 1
        try:
            t1 = s2._get_tricorder(str(r1))
            store1 = t1._db_store
            assert store1 is not None  # in-memory DB, no canonical DB
            s2._get_tricorder(str(r2))  # evicts r1
            assert t1._db_store is None  # closed + disarmed
            with pytest.raises(sqlite3.ProgrammingError):
                store1.conn.execute("SELECT 1")
        finally:
            s2._TRICORDER_CACHE_MAX = old_max
    finally:
        for t in list(srv._tricorder_cache.values()):
            try:
                t[2]._db_store.close()
            except Exception:
                pass
        srv._tricorder_cache.clear()


def _close_spy(monkeypatch):
    calls = []
    real_close = getattr(Tricorder, "close", None)

    def spy(self):
        calls.append(1)
        if real_close is not None:
            real_close(self)

    monkeypatch.setattr(Tricorder, "close", spy, raising=False)
    return calls


def test_tricorder_diff_closes_dedicated_instance():
    """tricorder_diff builds a dedicated read-only Tricorder per call; it
    must be closed afterwards, not leak a handle per call."""
    d = _repo(1)
    mp = pytest.MonkeyPatch()
    calls = _close_spy(mp)
    try:
        resp = asyncio.run(srv.tricorder_diff(str(d)))
    finally:
        mp.undo()
    assert "error" not in resp
    assert calls, "dedicated diff Tricorder was never closed"


def test_scan_tool_closes_mapper():
    """tricorder_scan builds its own Tricorder per call (not via the
    cache); it must be closed afterwards."""
    d = _repo(2)
    mp = pytest.MonkeyPatch()
    calls = _close_spy(mp)
    try:
        resp = asyncio.run(srv.tricorder_scan(
            project_root=str(d), other_files=["f0.py", "f1.py"],
            dry_run=True))
    finally:
        mp.undo()
    assert "error" not in resp, resp.get("error")
    assert calls, "scan Tricorder was never closed"


def test_keyboard_interrupt_clean_exit(monkeypatch):
    """Ctrl+C during a scan: no traceback, DB left closed, exit 130."""
    import tricorder as cli
    d = _repo(3)

    def _boom(self, *a, **k):
        raise KeyboardInterrupt

    monkeypatch.setattr(Tricorder, "get_ranked_tags", _boom)
    monkeypatch.setattr(sys, "argv", ["tricorder", "--root", str(d)])
    with pytest.raises(SystemExit) as exc:
        cli.main()
    assert exc.value.code == 130


def test_db_coverage_never_tags_distinct(monkeypatch, capsys):
    """House rule: coverage = COUNT(*) FROM file_state, never tags-distinct.

    A pre-Goal-3 DB (tags but no file_state table) must report unmapped
    (no output), not a tags-distinct file count.
    """
    import sqlite3
    import tricorder as cli
    d = _repo(1)
    dbdir = d / ".tricorder" / "db"
    dbdir.mkdir(parents=True)
    p = dbdir / (d.name + ".db")
    con = sqlite3.connect(str(p))
    con.execute("CREATE TABLE tags(file TEXT, rel_file TEXT, line INT, name TEXT, kind TEXT)")
    con.execute("CREATE TABLE meta(schema_version INT, root TEXT, signature TEXT, extractor_version INT)")
    con.execute("INSERT INTO tags VALUES ('x', 'f0.py', 1, 'func0', 'def')")
    con.execute("INSERT INTO meta VALUES (1, ?, 'sig', 2)", (str(d),))
    con.commit()
    con.close()
    monkeypatch.setattr(sys, "argv",
                        ["tricorder", "--root", str(d), "--db-coverage"])
    with pytest.raises(SystemExit):
        cli.main()
    out = capsys.readouterr().out
    assert out == "", f"expected no coverage output, got: {out!r}"
