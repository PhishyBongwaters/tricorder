"""Round 9: MCP cache thread-safety, --init --wipe vs a server-held DB,
plugin read-only URI opens with special characters in the path."""
import importlib
import os
import sys
import tempfile
import threading
import time
import types
from pathlib import Path

import pytest

from database import DBStore
import tricorder_server as srv


def _make_db(path, root, files):
    db = DBStore(str(path))
    db.set_meta(str(root), "sig-" + Path(root).name)
    for rel in files:
        db.set_file_state(rel, 100, 1234567890)
    db.conn.commit()
    db.conn.close()


def _import_plugin():
    """Import plugins.tricorder with hermes config faked (as in
    test_surface_parity), return (module, teardown)."""
    fake_cfg = {'plugins': {'entries': {'tricorder': {}}}}
    sys.modules['hermes_cli.config'] = types.SimpleNamespace(
        load_config=lambda: fake_cfg)
    sys.modules['hermes_constants'] = types.SimpleNamespace(
        get_hermes_home=lambda: Path(tempfile.mkdtemp()))
    plugin = importlib.import_module('plugins.tricorder')
    old_cfg, old_home = None, None  # hermes was never really installed here

    def teardown():
        sys.modules.pop('hermes_cli.config', None)
        sys.modules.pop('hermes_constants', None)
        sys.modules.pop('plugins.tricorder', None)
    return plugin, teardown


# --- 1. _get_tricorder must be safe under concurrent first hits ---------------
# Tool handlers run via asyncio.to_thread: two threads racing a cold root
# must not build two Tricorders (9s+ each) or corrupt the LRU.

def test_get_tricorder_concurrent_first_hit_builds_once(tmp_path, monkeypatch):
    root = tmp_path / "proj"
    root.mkdir()
    srv._tricorder_cache.clear()
    monkeypatch.setattr(srv, "_TRICORDER_CACHE_MAX", 32)
    try:
        constructions = []
        gate = threading.Barrier(8)

        class FakeTricorder:
            def __init__(self, **kwargs):
                time.sleep(0.3)  # widen the race window pre-fix
                constructions.append(kwargs.get("root"))
                self._db_store = None

        monkeypatch.setattr(srv, "Tricorder", FakeTricorder)
        results, errors = [], []

        def worker():
            try:
                gate.wait(timeout=10)
                results.append(srv._get_tricorder(str(root)))
            except Exception as e:  # noqa: BLE001
                errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)
        assert not errors, errors
        assert len(constructions) == 1, constructions
        assert all(r is results[0] for r in results)
    finally:
        srv._tricorder_cache.clear()


def test_tier_history_concurrent_access_no_crash(monkeypatch):
    srv._tier_history_store.clear()
    monkeypatch.setattr(srv, "_MAX_TIER_HISTORY", 16)
    errors = []
    stop = threading.Event()

    def churn(n):
        try:
            i = 0
            while not stop.is_set():
                key = f"root-{n}-{i % 64}"
                srv._tier_history_set(key, {"v": i})
                srv._tier_history_get(key)
                i += 1
        except Exception as e:  # noqa: BLE001
            errors.append(e)

    threads = [threading.Thread(target=churn, args=(n,)) for n in range(8)]
    for t in threads:
        t.start()
    time.sleep(1.0)
    stop.set()
    for t in threads:
        t.join(timeout=10)
    srv._tier_history_store.clear()
    assert not errors, errors[:3]


# --- 2. --init --wipe while the server holds the DB ---------------------------
# POSIX: unlink succeeds but the server's connection keeps writing to the
# unlinked inode; the same path now points at a NEW file. The server must
# detect the replacement (dev+ino change) and rebuild instead of serving
# the stale handle.

def test_get_tricorder_rebuilds_when_db_file_replaced(tmp_path, monkeypatch):
    root = tmp_path / "proj"
    root.mkdir()
    cachedb = tmp_path / "cachedb"
    cachedb.mkdir()
    monkeypatch.setattr(srv, "PRE_SCAN_DB_DIR", cachedb)
    dbpath = cachedb / "proj.db"
    _make_db(dbpath, root, ["a.py"])
    srv._tricorder_cache.clear()
    try:
        t1 = srv._get_tricorder(str(root))
        assert t1._db_store is not None
        assert "a.py" in t1._db_store.get_file_state()

        # --init --wipe: same path, new inode, different content
        os.unlink(dbpath)
        _make_db(dbpath, root, ["a.py", "b.py"])

        t2 = srv._get_tricorder(str(root))
        assert t2 is not t1, "server kept the stale unlinked-inode instance"
        assert "b.py" in t2._db_store.get_file_state()

        # the orphaned handle must be closed, not left writing to nowhere
        with pytest.raises(Exception):
            t1._db_store.get_file_state()
    finally:
        srv._tricorder_cache.clear()


def test_init_wipe_locked_db_clean_error(tmp_path, monkeypatch, capsys):
    """Windows: unlink fails when the server holds the DB open. Must be a
    clean parser error, not a traceback."""
    import tricorder as cli_mod
    import utils
    root = tmp_path / "proj"
    root.mkdir()
    cache = tmp_path / "tcache"
    monkeypatch.setattr(utils, "_CACHE_ROOT", None)
    monkeypatch.setenv("TRICORDER_CACHE_HOME", str(cache))
    dbdir = cache / "db"
    dbdir.mkdir(parents=True)
    (dbdir / "proj.db").touch()  # --wipe only unlinks an existing DB
    real_unlink = Path.unlink

    def fake_unlink(self, *a, **k):
        if self.suffix == ".db":
            raise PermissionError(13, "The process cannot access the file")
        return real_unlink(self, *a, **k)

    monkeypatch.setattr(Path, "unlink", fake_unlink)
    monkeypatch.setattr(
        sys, "argv",
        ["tricorder.py", "--root", str(root), "--init", "--wipe"])
    with pytest.raises(SystemExit) as ei:
        cli_mod.main()
    assert ei.value.code == 2
    err = capsys.readouterr().err.lower()
    assert "another process" in err or "held open" in err


# --- 3. plugin read-only opens with '#', '?' in the path ----------------------
# The plugin can't import tricorder in-process, so it inlines the URI form;
# that inline copy had no regression test.

def test_plugin_db_uri_survives_special_chars(tmp_path, monkeypatch):
    import utils
    root = tmp_path / "we#ird?repo"
    root.mkdir()
    cache = tmp_path / "tcache"
    monkeypatch.setattr(utils, "_CACHE_ROOT", None)
    monkeypatch.setenv("TRICORDER_CACHE_HOME", str(cache))
    dbdir = cache / "db"
    dbdir.mkdir(parents=True)
    dbpath = dbdir / "we#ird?repo.db"
    _make_db(dbpath, root, ["a.py"])
    plugin, teardown = _import_plugin()
    try:
        found = plugin._tricorder_db_for(str(root))
        assert found == str(dbpath), (
            "plugin failed to open a DB whose path contains '#'/'?'")
        line = plugin._db_coverage_line(str(dbpath), str(root))
        assert "mapped: 1 files" in line
    finally:
        teardown()
