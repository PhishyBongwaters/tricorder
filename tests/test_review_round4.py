"""Review round 4 (fresh-eyes pass): unwritable-DB guard parity, Windows
writability probe, immutable read-only opens, case-insensitive rel
matching, --diff/--root CLI hardening, and the break-even advisory."""
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database import DBStore, drop_mapped_files
from utils import _db_writable, db_root_matches, read_only_connect

REPO = Path(__file__).resolve().parent
CLI = str(REPO.parent / "tricorder.py")
PY = sys.executable


def _cli(*args):
    return subprocess.run(
        [PY, CLI, *args], capture_output=True, text=True, timeout=180)


class TestMcpUnwritableDbGuard(unittest.TestCase):
    """The MCP server must degrade like the CLI when the canonical DB
    exists but isn't writable."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="mcp_ro_db_"))
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
        _srv._tricorder_cache.clear()
        self.addCleanup(_srv._tricorder_cache.clear)

    def test_get_tricorder_degrades_to_memory(self):
        import tricorder_server as srv
        with mock.patch.object(srv, "_db_writable", return_value=False):
            tr = srv._get_tricorder(str(self.tmp))
        self.assertIsNone(tr._db_path,
                          "unwritable canonical DB must degrade MCP to in-memory")

    def test_get_tricorder_keeps_writable_db(self):
        import tricorder_server as srv
        tr = srv._get_tricorder(str(self.tmp))
        self.assertEqual(tr._db_path, str(self.db))


class TestDbWritableProbe(unittest.TestCase):
    """_db_writable must prove directory writability with a probe file:
    os.access(dir, W_OK) is existence-only on Windows."""

    def test_probe_failure_means_unwritable(self):
        d = Path(tempfile.mkdtemp(prefix="wprobe_"))
        self.addCleanup(shutil.rmtree, d, ignore_errors=True)
        target = str(d / "x.db")
        with mock.patch("tempfile.mkstemp", side_effect=PermissionError):
            self.assertFalse(_db_writable(target),
                             "probe failure must report unwritable")

    def test_probe_success_means_writable(self):
        d = Path(tempfile.mkdtemp(prefix="wprobe_"))
        self.addCleanup(shutil.rmtree, d, ignore_errors=True)
        self.assertTrue(_db_writable(str(d / "x.db")))
        # Non-vacuous: the probe file is cleaned up.
        self.assertEqual(list(d.iterdir()), [])

    def test_unwritable_file_still_detected(self):
        d = Path(tempfile.mkdtemp(prefix="wprobe_"))
        self.addCleanup(shutil.rmtree, d, ignore_errors=True)
        f = d / "x.db"
        f.write_text("x", encoding="utf-8")
        with mock.patch("os.access", return_value=False):
            self.assertFalse(_db_writable(str(f)))


class TestImmutableReadOnly(unittest.TestCase):
    """Read-only DB opens must use immutable=1: WAL sidecars can't be
    created in the read-only-checkout case the guard targets."""

    def _wal_db(self):
        d = Path(tempfile.mkdtemp(prefix="ro_imm_"))
        self.addCleanup(shutil.rmtree, d, ignore_errors=True)
        p = str(d / "idx.db")
        store = DBStore(p)
        try:
            store.set_meta(str(d), "sig", 2)
            store.commit()
        finally:
            store.close()
        return p, str(d)

    def test_db_root_matches_uses_immutable(self):
        p, root = self._wal_db()
        with mock.patch("sqlite3.connect") as m:
            m.return_value.execute.return_value.fetchone.return_value = (root,)
            db_root_matches(p, root)
        uri = m.call_args[0][0]
        self.assertIn("immutable=1", uri)

    def test_read_only_connect_uses_immutable(self):
        p, _ = self._wal_db()
        with mock.patch("sqlite3.connect") as m:
            read_only_connect(p).close()
        uri = m.call_args[0][0]
        self.assertIn("mode=ro", uri)
        self.assertIn("immutable=1", uri)


class TestRelCaseInsensitive(unittest.TestCase):
    """drop_mapped_files must match rels case-insensitively where the
    platform is case-insensitive (Windows): stored rels come from
    Path.relative_to, compared rels from os.path.relpath."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="relcase_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.f = str(self.tmp / "f0.py")
        Path(self.f).write_text("x = 1\n", encoding="utf-8")
        p = str(self.tmp / "idx.db")
        db = DBStore(p)
        try:
            db.set_file_state("F0.PY", 10, 123)
            db.commit()
        finally:
            db.close()
        self.dbp = p

    def test_normcase_applies_to_both_sides(self):
        with mock.patch("os.path.normcase", side_effect=lambda s: s.lower()):
            kept = drop_mapped_files([self.f], self.tmp, self.dbp)
        self.assertEqual(kept, [],
                         "case-mismatched rel must still match on a "
                         "case-insensitive platform")


class TestDiffExplicitDbPath(unittest.TestCase):
    """--diff is read-only: naming a nonexistent --db-path must fail clean,
    never create+initialize the file."""

    def test_diff_missing_explicit_db_errors(self):
        tmp = Path(tempfile.mkdtemp(prefix="diff_nodb_"))
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        (tmp / "a.py").write_text("x = 1\n", encoding="utf-8")
        missing = tmp / "nope.db"
        r = _cli("--root", str(tmp), "--diff", "--db-path", str(missing))
        self.assertNotEqual(r.returncode, 0,
                            "--diff with a missing --db-path must fail")
        self.assertFalse(missing.exists(),
                         "--diff must never create the DB file")


class TestRootValidationEarly(unittest.TestCase):
    """--root pointing at a non-directory must fail with the clean
    parser.error even for early-exit flags like --init."""

    def test_init_root_file_clean_error(self):
        tmp = Path(tempfile.mkdtemp(prefix="rootval_"))
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        f = tmp / "notadir.txt"
        f.write_text("x", encoding="utf-8")
        r = _cli("--init", "--root", str(f))
        self.assertEqual(r.returncode, 2,
                         "--init --root <file> must be a usage error, not a traceback")
        self.assertIn("not an existing directory", r.stderr)
        self.assertNotIn("Traceback", r.stderr)


class TestBreakEvenAdvisory(unittest.TestCase):
    def test_small_repo_claim_is_derived(self):
        from tricorder_server import _scan_break_even_advisory
        msg = _scan_break_even_advisory(76)
        self.assertIsNotNone(msg)
        self.assertNotIn("10+", msg,
                         "the '10+ queries' threshold has no basis in the benches")
        self.assertIn("negative", msg,
                      "the 76-file bench measured negative per-query returns")


if __name__ == "__main__":
    unittest.main()
