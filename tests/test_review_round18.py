"""Round-18 fresh-eyes review tests (red-first).

1. The per-file tags diskcache (and the file-text cache) still key on
   float seconds from get_mtime(): float st_mtime has ~238ns granularity
   at this epoch, so two same-size edits inside one quantum conflate and
   the cache serves stale tags/text. Round 16 moved file_state, the
   dirty-diff and the render cache to st_mtime_ns but left this cache
   behind -- the same permanent-staleness failure mode through a
   different door.
2. Warm-DB no-dirty scan drops tagless files from `included`: that branch
   filtered by stored_rels (files owning tag rows), so on every scan
   after the first, tagless files vanish from untagged_files and from the
   map's "Other files" section.
"""
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import Tricorder  # noqa: E402


def _tc(root, monkeypatch, cache_home, **kw):
    monkeypatch.setenv("TRICORDER_CACHE_HOME", str(cache_home))
    return Tricorder(root=str(root), **kw)


def test_tags_cache_ns_key_same_size_sub_float_quantum_edit(tmp_path, monkeypatch):
    """Same-size edits <238ns apart must not serve stale cached tags."""
    cache_home = tmp_path / "cachehome"
    cache_home.mkdir()
    repo = tmp_path / "repo"
    repo.mkdir()
    target = repo / "a.py"
    target.write_text("def foo():\n    pass\n")  # 21 bytes
    base_ns = 1_750_000_000_000_000_000
    os.utime(target, ns=(base_ns, base_ns))
    st1 = target.stat().st_mtime_ns
    if st1 != base_ns:
        pytest.skip("filesystem does not preserve ns mtimes")

    t1 = _tc(repo, monkeypatch, cache_home, use_db=True, db_path=None)
    names1 = [t.name for t in t1.get_tags(str(target), "a.py")]
    assert names1 == ["foo"], names1
    size1 = target.stat().st_size
    t1.close()

    # Same byte size, different symbol, mtime 100ns later.
    target.write_text("def bar():\n    pass\n")
    assert target.stat().st_size == size1
    os.utime(target, ns=(base_ns + 100, base_ns + 100))
    st2 = target.stat().st_mtime_ns
    assert st2 == base_ns + 100, "fs lost the +100ns bump"
    # The red precondition: float seconds really do conflate the two mtimes.
    assert float(st1) / 1e9 == float(st2) / 1e9, "no float conflation; test is vacuous"

    t2 = _tc(repo, monkeypatch, cache_home, use_db=True, db_path=None)
    try:
        names2 = [t.name for t in t2.get_tags(str(target), "a.py")]
    finally:
        t2.close()
    assert names2 == ["bar"], f"stale tags served from diskcache: {names2}"


def test_file_text_cache_ns_key(tmp_path, monkeypatch):
    """get_file_text must also miss on a sub-quantum same-size edit."""
    cache_home = tmp_path / "cachehome"
    cache_home.mkdir()
    repo = tmp_path / "repo"
    repo.mkdir()
    target = repo / "a.py"
    target.write_text("x = 1\n")
    base_ns = 1_750_000_000_000_000_000
    os.utime(target, ns=(base_ns, base_ns))
    st1 = target.stat().st_mtime_ns
    if st1 != base_ns:
        pytest.skip("filesystem does not preserve ns mtimes")

    t1 = _tc(repo, monkeypatch, cache_home, use_db=True, db_path=None)
    assert t1.get_file_text(str(target)) == "x = 1\n"
    t1.close()

    target.write_text("x = 2\n")
    os.utime(target, ns=(base_ns + 100, base_ns + 100))
    st2 = target.stat().st_mtime_ns
    assert st2 == base_ns + 100
    assert float(st1) / 1e9 == float(st2) / 1e9, "no float conflation; test is vacuous"

    t2 = _tc(repo, monkeypatch, cache_home, use_db=True, db_path=None)
    try:
        text = t2.get_file_text(str(target))
    finally:
        t2.close()
    assert text == "x = 2\n", f"stale file text served: {text!r}"


def test_warm_scan_keeps_tagless_files_included(tmp_path, monkeypatch):
    """A no-change second scan must still report tagless files as untagged."""
    cache_home = tmp_path / "cachehome"
    cache_home.mkdir()
    monkeypatch.setenv("TRICORDER_CACHE_HOME", str(cache_home))
    repo = tmp_path / "repo"
    repo.mkdir()
    a_py = repo / "a.py"
    a_py.write_text("def foo():\n    pass\n")
    empty_py = repo / "empty.py"
    empty_py.write_text("# nothing to see here\n")
    db_path = str(tmp_path / "idx.db")

    t = Tricorder(root=str(repo), use_db=True, db_path=db_path)
    try:
        _, report1 = t.get_ranked_tags([], [str(a_py), str(empty_py)])
        assert "empty.py" in report1.untagged_files, report1.untagged_files

        # Second scan, nothing changed -> warm-DB no-dirty path.
        _, report2 = t.get_ranked_tags([], [str(a_py), str(empty_py)])
        assert "empty.py" in report2.untagged_files, (
            f"tagless file dropped on warm scan: {report2.untagged_files}")
        assert report2.total_files_considered == 2
    finally:
        t.close()
