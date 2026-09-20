"""Review round 16: sub-second mtime granularity in file_state fingerprints.

file_state stored (size, int(mtime)) — mtime truncated to whole seconds. An
edit that lands in the same wall-clock second with the same byte size is
invisible to the incremental rescan AND --diff: stale tags are served
forever, with no signal that anything is wrong.

Red tests: after a same-size edit with the mtime pinned to its original
value via os.utime (a deterministic stand-in for a same-second edit), the
dirty diff must mark the file dirty and an incremental rescan must serve
the new tags.
"""
import os
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import Tricorder
from database import DBStore

OLD = "def alpha():\n    return 1\n"
NEW = "def omega():\n    return 1\n"  # same byte size as OLD, different symbol
assert len(OLD) == len(NEW)


def _make_repo():
    tmp = Path(tempfile.mkdtemp(prefix="r16_mtime_"))
    (tmp / ".tricorder").mkdir()
    (tmp / "a.py").write_text(OLD, encoding="utf-8")
    return tmp


def _pin_mtime(path: Path):
    """Simulate a same-second, same-size edit: the file gets new content,
    but its mtime keeps the same whole-second value with different
    nanoseconds — exactly what a real sub-second edit looks like on a
    filesystem with ns timestamps."""
    st = os.stat(path)
    path.write_text(NEW, encoding="utf-8")
    sec = int(st.st_mtime)
    new_ns = sec * 10**9 + 123_456_789  # same second, different ns
    os.utime(path, ns=(st.st_atime_ns, new_ns))
    st2 = os.stat(path)
    assert st2.st_size == st.st_size
    assert int(st2.st_mtime) == sec, "must stay within the same second"
    assert st2.st_mtime_ns != st.st_mtime_ns, "ns must differ (else nothing to detect)"


def _scan(root: Path, db_path: str):
    t = Tricorder(root=str(root), db_path=db_path, verbose=False)
    try:
        fnames = [str(root / "a.py")]
        ranked, _report = t.get_ranked_tags([], fnames)
        return [tag.name for _rank, tag in ranked]
    finally:
        t.close()


def test_diff_detects_same_second_edit(tmp_path=None):
    tmp = _make_repo()
    try:
        db_path = str(tmp / ".tricorder" / "idx.db")
        _scan(tmp, db_path)
        _pin_mtime(tmp / "a.py")
        t = Tricorder(root=str(tmp), db_path=db_path, verbose=False)
        try:
            d = t.diff_against_index(include_tags=False)
        finally:
            t.close()
        assert d["modified"] == ["a.py"], (
            f"same-second same-size edit invisible to --diff: {d}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_incremental_rescan_picks_up_same_second_edit():
    tmp = _make_repo()
    try:
        db_path = str(tmp / ".tricorder" / "idx.db")
        names1 = _scan(tmp, db_path)
        assert "alpha" in names1
        _pin_mtime(tmp / "a.py")
        names2 = _scan(tmp, db_path)
        assert "omega" in names2, (
            f"incremental rescan served stale tags after same-second edit: {names2}")
        assert "alpha" not in names2
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_file_state_stores_ns_resolution():
    tmp = _make_repo()
    try:
        db_path = str(tmp / ".tricorder" / "idx.db")
        _scan(tmp, db_path)
        db = DBStore(db_path, read_only=True)
        try:
            state = db.get_file_state()
        finally:
            db.close()
        size, mtime = state["a.py"]
        assert size == len(OLD)
        # Nanosecond epoch values are ~1e18; whole-second values are ~1e9.
        # Second resolution is what makes same-second edits invisible.
        assert mtime > 10**12, f"file_state mtime lacks sub-second resolution: {mtime}"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
