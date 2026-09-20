"""Tests for the prefix-cap resume path: drop_mapped_files, --init
ownership stamping, and canonical-DB resumption without --db-path."""
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database import DBStore, drop_mapped_files
from tricorder import _canonical_db_for, _effective_db_path

REPO = Path(__file__).resolve().parent
CLI = str(REPO.parent / "tricorder.py")
PY = sys.executable


def _args(**kw):
    base = {"no_db": False, "db_path": None, "diff": False}
    base.update(kw)
    return SimpleNamespace(**base)


class TestDropMappedFiles(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="drop_mapped_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.files = [str(self.tmp / f"f{i}.py") for i in range(3)]
        for f in self.files:
            Path(f).write_text("x = 1\n", encoding="utf-8")

    def _db_with(self, rels):
        p = str(self.tmp / "idx.db")
        db = DBStore(p)
        try:
            for r in rels:
                db.set_file_state(r, 10, 123)
            db.commit()
        finally:
            db.close()
        return p

    def test_none_db_path_unchanged(self):
        self.assertEqual(drop_mapped_files(self.files, self.tmp, None), self.files)

    def test_missing_db_unchanged(self):
        self.assertEqual(
            drop_mapped_files(self.files, self.tmp, str(self.tmp / "nope.db")),
            self.files)

    def test_empty_db_unchanged(self):
        p = self._db_with([])
        self.assertEqual(drop_mapped_files(self.files, self.tmp, p), self.files)

    def test_drops_mapped_keeps_unmapped(self):
        p = self._db_with(["f0.py", "f2.py"])
        kept = drop_mapped_files(self.files, self.tmp, p)
        self.assertEqual(kept, [self.files[1]])
        # Non-vacuous: the drop actually removed something.
        self.assertLess(len(kept), len(self.files))

    def test_effective_db_path_prefers_explicit(self):
        p = self._db_with(["f0.py"])
        args = _args(db_path=p)
        self.assertEqual(_effective_db_path(args, self.tmp), p)

    def test_effective_db_path_no_db_forces_none(self):
        self._db_with(["f0.py"])
        args = _args(no_db=True)
        self.assertIsNone(_effective_db_path(args, self.tmp))


class TestCliCanonicalResume(unittest.TestCase):
    """--init stamps meta.root so the canonical DB is visible; bare
    --max-files runs then resume into it without --db-path."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="cli_resume_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        for i in range(6):
            (self.tmp / f"f{i}.py").write_text(
                f"def f{i}():\n    return {i}\n", encoding="utf-8")

    def _run(self, *args):
        return subprocess.run(
            [PY, CLI, "--root", str(self.tmp), *args],
            capture_output=True, text=True, timeout=180)

    def _canonical(self):
        return self.tmp / ".tricorder" / "db" / f"{self.tmp.name}.db"

    def _file_state_count(self):
        db = self._canonical()
        if not db.exists():
            return 0
        con = sqlite3.connect(str(db))
        try:
            return con.execute("SELECT COUNT(*) FROM file_state").fetchone()[0]
        finally:
            con.close()

    def test_init_stamps_meta_root_visible(self):
        p = self._run("--init")
        self.assertEqual(p.returncode, 0, p.stderr[-500:])
        con = sqlite3.connect(str(self._canonical()))
        try:
            row = con.execute(
                "SELECT root FROM meta ORDER BY rowid DESC LIMIT 1").fetchone()
        finally:
            con.close()
        self.assertIsNotNone(row, "--init must stamp meta.root")
        # And the canonical lookup must now see the DB (previously: None
        # until a scan wrote meta, silently disabling resumption).
        self.assertEqual(_canonical_db_for(str(self.tmp)), str(self._canonical()))

    def test_rising_caps_resume_into_canonical(self):
        # --max-files is a prefix cap (house rule): a fixed-cap rerun adds
        # zero; resumed scans need rising caps.
        self._run("--init")
        r1 = self._run("--max-files", "2", "--map-tokens", "100000", "--quiet")
        self.assertEqual(r1.returncode, 0, r1.stderr[-500:])
        self.assertEqual(self._file_state_count(), 2,
                         "first bare run must populate the canonical DB")
        r2 = self._run("--max-files", "4", "--map-tokens", "100000", "--quiet")
        self.assertEqual(r2.returncode, 0, r2.stderr[-500:])
        self.assertEqual(self._file_state_count(), 4,
                         "rising cap must extend the mapped prefix")
        # The second map covers the new prefix slice, not the first.
        self.assertNotIn("def f0", r2.stdout)
        self.assertNotIn("def f1", r2.stdout)
        self.assertIn("def f2", r2.stdout)

    def test_fixed_cap_rerun_adds_zero(self):
        self._run("--init")
        self._run("--max-files", "2", "--map-tokens", "100000", "--quiet")
        self.assertEqual(self._file_state_count(), 2)
        r2 = self._run("--max-files", "2", "--map-tokens", "100000", "--quiet")
        self.assertEqual(r2.returncode, 0, r2.stderr[-500:])
        self.assertEqual(self._file_state_count(), 2,
                         "fixed-cap rerun must add zero (prefix cap)")

    def test_no_db_leaves_canonical_untouched(self):
        self._run("--init")
        r = self._run("--max-files", "2", "--map-tokens", "100000",
                      "--quiet", "--no-db")
        self.assertEqual(r.returncode, 0, r.stderr[-500:])
        self.assertEqual(self._file_state_count(), 0,
                         "--no-db must not write the canonical DB")

    def test_init_rerun_preserves_indexed_stamp(self):
        # --init is documented as idempotent; re-running it on an indexed
        # DB must not downgrade the extractor stamp to 0 (which would force
        # a pointless full rescan) or touch the signature/file_state.
        from database import EXTRACTOR_VERSION
        self._run("--init")
        db_path = self._canonical()
        store = DBStore(str(db_path))
        try:
            store.set_meta(str(self.tmp), "sig", EXTRACTOR_VERSION)
            store.set_file_state("f0.py", 10, 123)
            store.commit()
        finally:
            store.close()
        p = self._run("--init")
        self.assertEqual(p.returncode, 0, p.stderr[-500:])
        con = sqlite3.connect(str(db_path))
        try:
            meta = con.execute(
                "SELECT root, signature, extractor_version FROM meta "
                "ORDER BY rowid DESC LIMIT 1").fetchone()
            n = con.execute("SELECT COUNT(*) FROM file_state").fetchone()[0]
        finally:
            con.close()
        self.assertEqual(meta[2], EXTRACTOR_VERSION,
                         "--init re-run must not reset the extractor stamp")
        self.assertEqual(meta[1], "sig",
                         "--init re-run must not blank the signature")
        self.assertEqual(n, 1, "--init re-run must not touch file_state")


class TestUnwritableCanonical(unittest.TestCase):
    """A canonical DB that exists but isn't writable must degrade the map
    path to in-memory (with a warning), not crash on the first write."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="ro_canonical_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        # Canonical DB with stamped ownership (what --init now produces).
        dbdir = self.tmp / ".tricorder" / "db"
        dbdir.mkdir(parents=True)
        self.db = dbdir / f"{self.tmp.name}.db"
        store = DBStore(str(self.db))
        try:
            store.set_meta(str(self.tmp), "", 0)
            store.commit()
        finally:
            store.close()

    def _patch_unwritable(self):
        # os.access reports writable as root; simulate the non-root
        # read-only case by patching the writability probe itself.
        return mock.patch("tricorder._db_writable", return_value=False)

    def test_db_writable_true_for_writable(self):
        from tricorder import _db_writable
        self.assertTrue(_db_writable(str(self.db)))

    def test_for_write_skips_unwritable_canonical(self):
        with self._patch_unwritable():
            self.assertIsNone(_effective_db_path(_args(), self.tmp, for_write=True))

    def test_reader_keeps_unwritable_canonical(self):
        # --diff never updates the index, so a read-only DB stays usable.
        with self._patch_unwritable():
            self.assertEqual(
                _effective_db_path(_args(), self.tmp, for_write=False),
                str(self.db))

    def test_explicit_db_path_ignores_guard(self):
        with self._patch_unwritable():
            self.assertEqual(
                _effective_db_path(_args(db_path="/x.db"), self.tmp, for_write=True),
                "/x.db")

    def test_warning_fires_on_degradation(self):
        from tricorder import _unwritable_canonical_warning
        with self._patch_unwritable():
            scan_db_path = _effective_db_path(_args(), self.tmp, for_write=True)
            msg = _unwritable_canonical_warning(_args(), self.tmp, scan_db_path)
        self.assertIsNotNone(msg, "degradation must warn")
        self.assertIn("not writable", msg)
        # Non-vacuous: no warning when the DB is usable...
        scan_db_path = _effective_db_path(_args(), self.tmp, for_write=True)
        self.assertEqual(scan_db_path, str(self.db))
        self.assertIsNone(
            _unwritable_canonical_warning(_args(), self.tmp, scan_db_path))
        # ...or when the canonical DB isn't in play at all.
        self.assertIsNone(
            _unwritable_canonical_warning(_args(no_db=True), self.tmp, None))
        self.assertIsNone(
            _unwritable_canonical_warning(_args(diff=True), self.tmp, None))


if __name__ == "__main__":
    unittest.main()
