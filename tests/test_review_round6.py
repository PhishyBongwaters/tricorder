"""Review round 6 (fresh-eyes pass): the MCP scan path never got the
unwritable-canonical-DB guard (it crashed while the drop window treated
the DB as absent); --diff/tricorder_diff claimed read-only but opened the
DB read-write via DBStore (DDL+commit at init crashed on read-only
checkouts); and --diff --db-path <directory> slipped past the existence
guard into a sqlite traceback."""
import asyncio
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database import DBStore

REPO = Path(__file__).resolve().parent
CLI = str(REPO.parent / "tricorder.py")
PY = sys.executable


def _cli(*args, env=None):
    e = dict(os.environ)
    if env:
        e.update(env)
    return subprocess.run(
        [PY, CLI, *args], capture_output=True, text=True, timeout=180, env=e)


def _make_canonical_db(tmp, files):
    """Write files, then build a populated canonical index DB for the repo
    (like a finished scan would leave it): meta stamped, file_state set
    from real file stats, checkpointed on close so immutable=1 readers
    see everything."""
    for name, text in files.items():
        (tmp / name).write_text(text, encoding="utf-8")
    dbdir = tmp / ".tricorder" / "db"
    dbdir.mkdir(parents=True, exist_ok=True)
    db = dbdir / f"{tmp.name}.db"
    store = DBStore(str(db))
    try:
        store.set_meta(str(tmp), "", 0)
        for name in files:
            st = os.stat(tmp / name)
            store.set_file_state(name, st.st_size, int(st.st_mtime))
        store.commit()
    finally:
        store.close()
    return db


class TestDbStoreReadOnly(unittest.TestCase):
    """DBStore(path, read_only=True) must never open the DB read-write:
    no DDL, no migration, no commit — the frozen open rejects writes."""

    def _db(self):
        d = Path(tempfile.mkdtemp(prefix="ro6_"))
        self.addCleanup(shutil.rmtree, d, ignore_errors=True)
        p = str(d / "idx.db")
        store = DBStore(p)
        try:
            store.set_meta(str(d), "sig", 2)
            store.set_file_state("a.py", 10, 123)
            store.commit()
        finally:
            store.close()
        return p

    def test_read_only_reads_without_read_write_open(self):
        p = self._db()
        real_connect = sqlite3.connect

        def guarded(*a, **kw):
            target = a[0] if a else kw.get("database", "")
            if isinstance(target, str) and target.startswith("file:") and kw.get("uri"):
                return real_connect(*a, **kw)
            raise sqlite3.OperationalError("attempt to write a readonly database")

        with mock.patch("sqlite3.connect", side_effect=guarded):
            store = DBStore(p, read_only=True)
            try:
                meta = store.get_meta()
                self.assertIsNotNone(meta, "read-only open must read meta")
                self.assertEqual(store.get_file_state(), {"a.py": (10, 123)})
                with self.assertRaises(sqlite3.OperationalError):
                    store.set_file_state("b.py", 1, 2)
            finally:
                store.close()

    def test_read_only_requires_a_path(self):
        with self.assertRaises(ValueError):
            DBStore(None, read_only=True)

    def test_read_only_does_not_create_missing_db(self):
        d = Path(tempfile.mkdtemp(prefix="ro6miss_"))
        self.addCleanup(shutil.rmtree, d, ignore_errors=True)
        missing = str(d / "nope.db")
        with self.assertRaises(sqlite3.OperationalError):
            DBStore(missing, read_only=True)
        self.assertFalse(Path(missing).exists(),
                         "read-only open must never create the file")


class TestMcpScanUnwritableGuard(unittest.TestCase):
    """tricorder_scan must degrade to in-memory (like _get_tricorder and
    the CLI) when the canonical DB exists but isn't writable — the scan
    path constructs its own Tricorder, so it needs the guard too."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="mcp6_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        (self.tmp / "a.py").write_text("x = 1\n", encoding="utf-8")
        dbdir = self.tmp / ".tricorder" / "db"
        dbdir.mkdir(parents=True)
        self.db = dbdir / f"{self.tmp.name}.db"
        store = DBStore(str(self.db))
        try:
            store.set_meta(str(self.tmp), "", 0)
            store.commit()
        finally:
            store.close()
        import tricorder_server as _srv
        _srv._get_tricorder.cache_clear()
        _srv._canonical_db_for.cache_clear()
        self.addCleanup(_srv._get_tricorder.cache_clear)
        self.addCleanup(_srv._canonical_db_for.cache_clear)

    def test_scan_degrades_to_memory(self):
        import tricorder_server as srv
        real_tricorder = srv.Tricorder
        seen = {}

        def spy(**kwargs):
            seen.update(kwargs)
            return real_tricorder(**kwargs)

        with mock.patch.object(srv, "_db_writable", return_value=False), \
             mock.patch.object(srv, "Tricorder", side_effect=spy):
            result = asyncio.run(srv.tricorder_scan(
                project_root=str(self.tmp), chat_files=["a.py"], dry_run=True))
        self.assertIsNone(seen.get("db_path"),
                          "unwritable canonical DB must degrade the MCP scan to in-memory")
        self.assertNotIn("error", result,
                         f"degraded scan must succeed, got: {result.get('error')}")


class TestMcpDiffReadOnly(unittest.TestCase):
    """tricorder_diff's docstring promises read-only ('it never updates
    the index') — it must open the DB frozen, not read-write."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="mcpdiff6_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.db = _make_canonical_db(
            self.tmp, {"a.py": "def foo():\n    return 1\n"})
        (self.tmp / "a.py").write_text(
            "def foo():\n    return 1\n\n\ndef bar():\n    return 2\n",
            encoding="utf-8")
        import tricorder_server as _srv
        _srv._get_tricorder.cache_clear()
        _srv._canonical_db_for.cache_clear()
        self.addCleanup(_srv._get_tricorder.cache_clear)
        self.addCleanup(_srv._canonical_db_for.cache_clear)

    def test_diff_opens_read_only(self):
        import tricorder_server as srv
        real_tricorder = srv.Tricorder
        seen = {}

        def spy(**kwargs):
            seen.update(kwargs)
            return real_tricorder(**kwargs)

        with mock.patch.object(srv, "Tricorder", side_effect=spy):
            result = asyncio.run(srv.tricorder_diff(project_root=str(self.tmp)))
        self.assertTrue(seen.get("db_read_only"),
                        "tricorder_diff must open the index read-only")
        self.assertNotIn("error", result,
                         f"diff must succeed, got: {result.get('error')}")
        self.assertIn("a.py", result.get("modified", []))


class TestDiffCliHardening(unittest.TestCase):
    """End-to-end as an unprivileged user: --diff against a read-only
    canonical DB must diff against the baseline (not crash), and --diff
    --db-path <directory> must fail clean."""

    @unittest.skipUnless(os.geteuid() == 0 and shutil.which("runuser"),
                         "needs root + runuser to drop privileges")
    def test_diff_against_read_only_canonical_db(self):
        tmp = Path(tempfile.mkdtemp(prefix="diffro6_"))
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        db = _make_canonical_db(tmp, {"a.py": "def foo():\n    return 1\n"})
        (tmp / "a.py").write_text(
            "def foo():\n    return 1\n\n\ndef bar():\n    return 2\n",
            encoding="utf-8")
        os.chmod(db, 0o444)
        # The unprivileged user must reach the repo, the CLI sources, and
        # the venv (root-owned, mode 700 in this container).
        venv = Path(PY).parent.parent  # no resolve(): venv python symlinks to /usr
        subprocess.run(["chmod", "-R", "a+rX", str(tmp)], check=True)
        subprocess.run(["chmod", "a+rX", "/home/hatch", "/home/hatch/workspace"],
                       check=True)
        subprocess.run(["chmod", "-R", "a+rX", str(REPO.parent), str(venv)],
                       check=True)
        home = tmp / "nobody_home"
        home.mkdir(mode=0o777, exist_ok=True)
        cache = tmp / "nobody_cache"
        cache.mkdir(mode=0o777, exist_ok=True)

        r = subprocess.run(
            ["runuser", "-u", "nobody", "--", "env",
             f"TRICORDER_CACHE_HOME={cache}", f"HOME={home}",
             PY, CLI, "--diff", "--root", str(tmp), "--format", "json"],
            capture_output=True, text=True, timeout=180)
        self.assertEqual(r.returncode, 0,
                         f"--diff on a read-only DB must not crash: {r.stderr[-2000:]}")
        self.assertNotIn("Traceback", r.stderr)
        diff = json.loads(r.stdout)
        self.assertTrue(diff.get("indexed"), "must diff against the real baseline")
        self.assertIn("a.py", diff.get("modified", []),
                      "the changed file must show as modified, not added")

    def test_diff_db_path_directory_fails_clean(self):
        tmp = Path(tempfile.mkdtemp(prefix="diffdir6_"))
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        (tmp / "a.py").write_text("x = 1\n", encoding="utf-8")
        r = _cli("--root", str(tmp), "--diff", "--db-path", str(tmp))
        self.assertEqual(r.returncode, 2,
                         "--diff --db-path <directory> must be a usage error, not a traceback")
        self.assertNotIn("Traceback", r.stderr)
        self.assertIn("no DB at", r.stderr)


if __name__ == "__main__":
    unittest.main()
