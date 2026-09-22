"""--db-coverage: shared-cache basename collisions are rejected, and coverage
counts file_state rows (house rule: never tags-distinct — tagless files own
zero tag rows)."""
import os
import subprocess
import sys
from pathlib import Path

from database import DBStore

CLI = str(Path(__file__).resolve().parent.parent / "tricorder.py")


def _make_db(path, root, files, tags=()):
    db = DBStore(str(path))
    db.set_meta(str(root), "deadbeefcafebabe")
    for rel in files:
        db.set_file_state(rel, 100, 1234567890)
    if tags:
        db.insert_tags(tags)
    db.conn.commit()
    db.conn.close()


def _run(root, env=None):
    return subprocess.run(
        [sys.executable, CLI, "--root", str(root), "--db-coverage"],
        capture_output=True, text=True, env=env,
    )


def test_db_coverage_rejects_shared_cache_collision(tmp_path):
    base_a = tmp_path / "a"
    base_b = tmp_path / "b"
    repo_a = (base_a / "proj").resolve()
    repo_b = (base_b / "proj").resolve()
    repo_a.mkdir(parents=True)
    repo_b.mkdir(parents=True)
    cache = tmp_path / "cache"
    (cache / "db").mkdir(parents=True)
    _make_db(cache / "db" / "proj.db", repo_a, ["a.py"])
    env = dict(os.environ, TRICORDER_CACHE_HOME=str(cache))

    # repo B shares the basename but must not inherit repo A's "mapped" claim
    r = _run(repo_b, env)
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == ""

    # repo A itself still reports coverage through the shared cache
    r = _run(repo_a, env)
    assert r.returncode == 0, r.stderr
    assert "mapped: 1 files" in r.stdout


def test_db_coverage_counts_file_state_not_tags(tmp_path):
    root = (tmp_path / "repo").resolve()
    root.mkdir(parents=True)
    cache = tmp_path / "cache"
    (cache / "db").mkdir(parents=True)
    # tagless files own zero tag rows, but the repo is still mapped
    _make_db(cache / "db" / "repo.db", root, ["a.py", "data.json"])
    env = dict(os.environ, TRICORDER_CACHE_HOME=str(cache))
    r = _run(root, env)
    assert r.returncode == 0, r.stderr
    assert "mapped: 2 files, 0 tags" in r.stdout


def test_db_coverage_unmapped_prints_nothing(tmp_path):
    root = (tmp_path / "empty").resolve()
    root.mkdir(parents=True)
    r = _run(root)
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == ""


def test_prescan_refuses_collision_overwrite(tmp_path):
    import pre_scan
    repo_a = (tmp_path / "a" / "proj").resolve()
    repo_b = (tmp_path / "b" / "proj").resolve()
    repo_a.mkdir(parents=True)
    repo_b.mkdir(parents=True)
    db = tmp_path / "proj.db"
    _make_db(db, repo_a, ["a.py"])
    # same repo may refresh its own DB; a same-named other repo may not
    # clobber it; an absent path is always writable
    assert pre_scan._db_free_for(db, repo_a) is True
    assert pre_scan._db_free_for(db, repo_b) is False
    assert pre_scan._db_free_for(tmp_path / "missing.db", repo_b) is True
