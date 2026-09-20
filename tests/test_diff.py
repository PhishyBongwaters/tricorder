"""Tests for delta maps: Tricorder.diff_against_index + tricorder_diff MCP tool."""
import asyncio
import os
import shutil
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import Tricorder
from database import DBStore


def _write(p: Path, text: str):
    p.write_text(text, encoding="utf-8")


class TestDiffAgainstIndex(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="diff_"))
        # Mirror production layout: the index DB lives under .tricorder/,
        # which discover_src_files skips (dot-dir rule).
        (self.tmp / ".tricorder").mkdir()
        self.db_path = str(self.tmp / ".tricorder" / "idx.db")
        _write(self.tmp / "a.py", "def alpha():\n    return 1\n")
        _write(self.tmp / "b.py", "def beta():\n    return 2\n")
        # Force distinct mtimes (filesystem granularity).
        time.sleep(0.02)
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def _index(self):
        """Record current file_state as if a scan just completed."""
        db = DBStore(self.db_path)
        for f in ("a.py", "b.py"):
            st = os.stat(self.tmp / f)
            db.set_file_state(f, st.st_size, st.st_mtime_ns)
        db.conn.commit()
        db.conn.close()

    def _tricorder(self):
        return Tricorder(root=str(self.tmp), db_path=self.db_path, verbose=False)

    def test_no_changes(self):
        self._index()
        d = self._tricorder().diff_against_index()
        self.assertTrue(d["indexed"])
        self.assertEqual(d["added"], [])
        self.assertEqual(d["modified"], [])
        self.assertEqual(d["deleted"], [])

    def test_index_db_inside_root_is_invisible(self):
        # A hand-placed --db-path inside the root must not pollute the
        # diff: the index file (and sqlite sidecars) are the thing being
        # compared against, not working-tree content.
        in_root_db = str(self.tmp / "idx.db")
        db = DBStore(in_root_db)
        for f in ("a.py", "b.py"):
            st = os.stat(self.tmp / f)
            db.set_file_state(f, st.st_size, st.st_mtime_ns)
        db.conn.commit()
        db.conn.close()
        # Touch sidecars the way a journal-mode sqlite DB would leave them.
        for suffix in ("-wal", "-shm"):
            (self.tmp / ("idx.db" + suffix)).write_text("x", encoding="utf-8")
        d = Tricorder(root=str(self.tmp), db_path=in_root_db,
                      verbose=False).diff_against_index()
        self.assertTrue(d["indexed"])
        self.assertEqual(d["added"], [])
        self.assertEqual(d["modified"], [])
        self.assertEqual(d["deleted"], [])

    def test_added_modified_deleted(self):
        self._index()
        time.sleep(0.02)
        _write(self.tmp / "a.py", "def alpha():\n    return 1\n\ndef gamma():\n    return 3\n")
        _write(self.tmp / "c.py", "x = 1\n")
        (self.tmp / "b.py").unlink()
        # Bump mtime explicitly (some filesystems have coarse granularity).
        now = time.time() + 5
        os.utime(self.tmp / "a.py", (now, now))

        d = self._tricorder().diff_against_index()
        self.assertEqual(d["added"], ["c.py"])
        self.assertEqual(d["modified"], ["a.py"])
        self.assertEqual(d["deleted"], ["b.py"])
        # Delta map carries tags for changed files only.
        self.assertIn("a.py", d["tags"])
        self.assertIn("c.py", d["tags"])
        self.assertNotIn("b.py", d["tags"])
        names = {t["name"] for t in d["tags"]["a.py"]}
        self.assertIn("alpha", names)
        self.assertIn("gamma", names)

    def test_never_scanned(self):
        d = self._tricorder().diff_against_index()
        self.assertFalse(d["indexed"])
        self.assertEqual(sorted(d["added"]), ["a.py", "b.py"])
        self.assertEqual(d["modified"], [])
        self.assertEqual(d["deleted"], [])

    def test_no_db(self):
        t = Tricorder(root=str(self.tmp), use_db=False, verbose=False)
        d = t.diff_against_index()
        self.assertFalse(d["indexed"])
        self.assertEqual(sorted(d["added"]), ["a.py", "b.py"])

    def test_mcp_tool(self):
        from tricorder_server import tricorder_diff
        self._index()
        result = asyncio.run(tricorder_diff(project_root=str(self.tmp)))
        # Server resolves the canonical DB; with a custom db_path there is
        # none, so it reports unindexed — but must not error.
        self.assertNotIn("error", result)
        self.assertIn("added", result)
        self.assertIn("modified", result)
        self.assertIn("deleted", result)

    def test_tags_capped_with_exact_counts(self):
        # Render diet: a 200-def changed file ships a 50-tag head, but the
        # exact total and the omitted count stay explicit — a trimmed list
        # never hides how much was dropped.
        big = "".join(f"def func_{i}():\n    return {i}\n" for i in range(200))
        _write(self.tmp / "big.py", big)
        self._index()
        # _index() only covers a.py/b.py: record big.py too, then modify it.
        db = DBStore(self.db_path)
        st = os.stat(self.tmp / "big.py")
        db.set_file_state("big.py", st.st_size, st.st_mtime_ns)
        db.conn.commit()
        db.conn.close()
        time.sleep(0.02)
        _write(self.tmp / "big.py", big + "\ndef extra():\n    return -1\n")
        now = time.time() + 5
        os.utime(self.tmp / "big.py", (now, now))

        d = self._tricorder().diff_against_index()
        self.assertEqual(d["modified"], ["big.py"])
        self.assertEqual(len(d["tags"]["big.py"]), 50)
        self.assertEqual(d["tag_counts"]["big.py"], 201)
        self.assertEqual(d["tags_omitted"]["big.py"], 151)
        self.assertTrue(d["tags_truncated"])
        # Small files are untouched by the cap and report no omissions.
        self.assertNotIn("a.py", d["tags_omitted"])
        # Internal consistency: total == head + omitted.
        self.assertEqual(d["tag_counts"]["big.py"],
                         len(d["tags"]["big.py"]) + d["tags_omitted"]["big.py"])

    def test_tags_uncapped_when_small(self):
        self._index()
        time.sleep(0.02)
        _write(self.tmp / "a.py", "def alpha():\n    return 1\n\ndef gamma():\n    return 3\n")
        now = time.time() + 5
        os.utime(self.tmp / "a.py", (now, now))
        d = self._tricorder().diff_against_index()
        names = {t["name"] for t in d["tags"]["a.py"]}
        self.assertIn("alpha", names)
        self.assertIn("gamma", names)
        self.assertFalse(d["tags_truncated"])
        self.assertEqual(d["tags_omitted"], {})

    def test_unindexed_diff_parses_no_tags(self):
        # Concise --diff on a never-scanned repo: without a baseline the
        # file list IS the delta — no full-repo tag inventory (which would
        # be a scan, not a diff).
        d = self._tricorder().diff_against_index()
        self.assertFalse(d["indexed"])
        self.assertEqual(sorted(d["added"]), ["a.py", "b.py"])
        self.assertEqual(d["tags"], {})
        self.assertEqual(d["tag_counts"], {})
        self.assertFalse(d["tags_truncated"])

    def test_include_tags_false_gives_file_lists_only(self):
        self._index()
        time.sleep(0.02)
        _write(self.tmp / "a.py", "def alpha():\n    return 1\n\ndef gamma():\n    return 3\n")
        now = time.time() + 5
        os.utime(self.tmp / "a.py", (now, now))
        d = self._tricorder().diff_against_index(include_tags=False)
        self.assertEqual(d["modified"], ["a.py"])
        self.assertEqual(d["tags"], {})
        self.assertEqual(d["tag_counts"], {})
        self.assertFalse(d["tags_truncated"])


class TestCliDiffAlias(unittest.TestCase):
    """--since is a pure alias for --diff at the CLI layer."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="diff_alias_"))
        (self.tmp / "a.py").write_text("def alpha():\n    return 1\n", encoding="utf-8")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.cli = str(Path(__file__).resolve().parent.parent / "tricorder.py")

    def _run(self, *args):
        import subprocess
        return subprocess.run(
            [sys.executable, self.cli, "--root", str(self.tmp), *args],
            capture_output=True, text=True, timeout=120,
        )

    def test_since_matches_diff(self):
        p_diff = self._run("--diff", "--format", "json")
        p_since = self._run("--since", "--format", "json")
        self.assertEqual(p_diff.returncode, 0, p_diff.stderr[-500:])
        self.assertEqual(p_since.returncode, 0, p_since.stderr[-500:])
        import json
        # No index DB here: both report every file as added, identically.
        self.assertEqual(json.loads(p_since.stdout), json.loads(p_diff.stdout))
        self.assertIn("added", json.loads(p_since.stdout))


class TestCanonicalDbRootGuard(unittest.TestCase):
    """Same folder name, different repos: the shared-cache DB lookup must not
    serve repo A's index for repo B. Canonical lookup is by directory
    basename, so a colliding cache DB whose meta.root mismatches is treated
    as absent (a rescan) instead of silently corrupting diff/detect/detail."""

    def setUp(self):
        # Scope the temp cache root so the in-process get_cache_root()
        # used by sibling tests is not polluted (test_issue40 pattern).
        self._saved_cache_home = os.environ.get("TRICORDER_CACHE_HOME")
        self._tmp_cache = Path(tempfile.mkdtemp(prefix="dbguard_cache_"))
        os.environ["TRICORDER_CACHE_HOME"] = str(self._tmp_cache)
        import utils
        utils._CACHE_ROOT = None  # force re-resolution under the temp root
        self._utils = utils
        self.tmp = Path(tempfile.mkdtemp(prefix="dbguard_"))
        self.repo_a = (self.tmp / "a" / "proj").resolve()
        self.repo_b = (self.tmp / "b" / "proj").resolve()
        self.repo_a.mkdir(parents=True)
        self.repo_b.mkdir(parents=True)
        _write(self.repo_a / "a.py", "def alpha():\n    return 1\n")
        _write(self.repo_b / "b.py", "def beta():\n    return 2\n")
        # Simulate a pre_scan cache DB for repo A (cache dir keyed by basename).
        cache_db_dir = utils.get_cache_root() / "db"
        cache_db_dir.mkdir(parents=True, exist_ok=True)
        self.cache_db = cache_db_dir / "proj.db"
        db = DBStore(str(self.cache_db))
        db.set_meta(str(self.repo_a), "sig")
        st = os.stat(self.repo_a / "a.py")
        db.set_file_state("a.py", st.st_size, st.st_mtime_ns)
        db.conn.commit()
        db.conn.close()
        # tricorder_server binds PRE_SCAN_DB_DIR at import time; in the full
        # suite it may already be imported (bound to the default cache root).
        # Rebind it to this test's temp cache so the server lookup sees the
        # same colliding DB the CLI lookup sees, and clear the lookup's
        # lru_cache so results can't leak between tests.
        import tricorder_server as srv
        self._srv = srv
        self._saved_pre_scan_dir = srv.PRE_SCAN_DB_DIR
        srv.PRE_SCAN_DB_DIR = utils.get_cache_root() / "db"
        # _canonical_db_for is intentionally uncached (round 8): no
        # cache_clear needed; results can't leak between tests.
        self.addCleanup(self._cleanup)

    def _cleanup(self):
        self._srv.PRE_SCAN_DB_DIR = self._saved_pre_scan_dir
        shutil.rmtree(self.tmp, ignore_errors=True)
        shutil.rmtree(self._tmp_cache, ignore_errors=True)
        if self._saved_cache_home is None:
            os.environ.pop("TRICORDER_CACHE_HOME", None)
        else:
            os.environ["TRICORDER_CACHE_HOME"] = self._saved_cache_home
        self._utils._CACHE_ROOT = None

    def test_db_root_matches_own_root(self):
        self.assertTrue(
            self._utils.db_root_matches(str(self.cache_db), str(self.repo_a)))

    def test_db_root_matches_rejects_other_root(self):
        self.assertFalse(
            self._utils.db_root_matches(str(self.cache_db), str(self.repo_b)))

    def test_db_root_matches_missing_db(self):
        self.assertFalse(self._utils.db_root_matches(
            str(self.cache_db) + ".nope", str(self.repo_a)))

    def test_db_root_matches_garbage_file(self):
        junk = self._tmp_cache / "junk.db"
        junk.write_text("not a database", encoding="utf-8")
        self.assertFalse(
            self._utils.db_root_matches(str(junk), str(self.repo_a)))

    def test_cli_canonical_db_rejects_collision(self):
        import tricorder as cli
        self.assertIsNone(cli._canonical_db_for(str(self.repo_b)))
        self.assertEqual(cli._canonical_db_for(str(self.repo_a)),
                         str(self.cache_db))

    def test_server_canonical_db_rejects_collision(self):
        import tricorder_server as srv
        self.assertIsNone(srv._canonical_db_for(str(self.repo_b)))
        self.assertEqual(srv._canonical_db_for(str(self.repo_a)),
                         str(self.cache_db))

    def test_diff_reports_unindexed_for_colliding_repo(self):
        # repo B must not inherit repo A's file_state: every file added,
        # indexed=False — never a silently wrong delta.
        import tricorder as cli
        db_path = cli._canonical_db_for(str(self.repo_b))
        t = Tricorder(root=str(self.repo_b), db_path=db_path, verbose=False)
        d = t.diff_against_index()
        self.assertFalse(d["indexed"])
        self.assertEqual(d["added"], ["b.py"])

    def test_scan_db_resolution_is_canonical(self):
        # tricorder_scan must use the same canonical lookup as the other
        # tools: an in-repo .tricorder/db/<name>.db wins over the shared
        # cache, and a colliding cache DB is still rejected for repo B.
        import tricorder_server as srv
        in_repo = self.repo_a / ".tricorder" / "db" / "proj.db"
        in_repo.parent.mkdir(parents=True, exist_ok=True)
        db = DBStore(str(in_repo))
        db.set_meta(str(self.repo_a), "sig")
        db.conn.commit()
        db.conn.close()
        # _canonical_db_for is uncached (round 8): no cache_clear needed.
        self.assertEqual(srv._canonical_db_for(str(self.repo_a)),
                         str(in_repo))
        self.assertIsNone(srv._canonical_db_for(str(self.repo_b)))


if __name__ == "__main__":
    unittest.main()
