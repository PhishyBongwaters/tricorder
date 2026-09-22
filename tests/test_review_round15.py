"""Review round 15: corrupt-DB handling must fail clean, never traceback.

Red tests: a garbage --db-path (or truncated sqlite file) must produce a
clean error + nonzero exit on the CLI scan/diff paths, not a raw
sqlite3.DatabaseError traceback; the --diff path must not silently report
"No scan index found" for a corrupt DB either (that message is a lie when
the file exists but is unreadable).
"""
import os
import re
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import DBStore

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TRICORDER = os.path.join(REPO_ROOT, "tricorder.py")
VENV_PY = sys.executable


def _write(path, data):
    with open(path, "wb") as f:
        f.write(data)


def test_corrupt_db_readwrite_raises_clean_error(tmp_path):
    bad = str(tmp_path / "bad.db")
    _write(bad, os.urandom(200))
    with pytest.raises(ValueError, match="[Nn]ot a SQLite database"):
        DBStore(bad)


def test_corrupt_db_readonly_raises_clean_error(tmp_path):
    bad = str(tmp_path / "bad.db")
    _write(bad, os.urandom(200))
    with pytest.raises(ValueError, match="[Nn]ot a SQLite database"):
        DBStore(bad, read_only=True)


def test_truncated_sqlite_header_raises_clean_error(tmp_path):
    # Valid magic but truncated/corrupt pages: the header check passes,
    # sqlite itself must still fail clean instead of raw DatabaseError.
    bad = str(tmp_path / "trunc.db")
    _write(bad, b"SQLite format 3\x00" + os.urandom(200))
    with pytest.raises(ValueError, match="[Nn]ot a SQLite database"):
        DBStore(bad)


def test_empty_db_file_still_initializes(tmp_path):
    # 0-byte file is a valid fresh DB for sqlite — must not regress.
    db = str(tmp_path / "empty.db")
    _write(db, b"")
    store = DBStore(db)
    try:
        assert store.get_meta() is None or True  # just needs to not raise
    finally:
        store.close()


def _make_repo(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "a.py").write_text("def hello():\n    pass\n")
    return str(repo)


def _run_cli(*args):
    return subprocess.run(
        [VENV_PY, TRICORDER, *args],
        capture_output=True, text=True, timeout=120,
        env={**os.environ, "TRICORDER_CACHE_HOME": str(os.path.join(
            os.environ.get("TMPDIR", "/tmp"), "r15-cli-cache"))},
    )


def test_cli_scan_corrupt_db_clean_error(tmp_path):
    bad = str(tmp_path / "bad.db")
    _write(bad, os.urandom(200))
    repo = _make_repo(tmp_path)
    proc = _run_cli("--db-path", bad, "--root", repo)
    out = proc.stdout + proc.stderr
    assert proc.returncode != 0, f"expected nonzero exit, got: {out[:500]}"
    assert "Traceback" not in out, f"raw traceback leaked: {out[:800]}"
    assert re.search(r"[Nn]ot a SQLite database", out), \
        f"clean message missing: {out[:800]}"


def test_cli_diff_corrupt_db_clean_error(tmp_path):
    bad = str(tmp_path / "bad.db")
    _write(bad, os.urandom(200))
    repo = _make_repo(tmp_path)
    proc = _run_cli("--db-path", bad, "--root", repo, "--diff")
    out = proc.stdout + proc.stderr
    assert proc.returncode != 0, f"expected nonzero exit, got: {out[:500]}"
    assert "Traceback" not in out, f"raw traceback leaked: {out[:800]}"
    assert re.search(r"[Nn]ot a SQLite database", out), \
        f"clean message missing: {out[:800]}"
    # The old behavior silently degraded to this lie; it must be gone.
    assert "No scan index found" not in out
