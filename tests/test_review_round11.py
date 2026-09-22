"""Round 11: extractor-version staleness vs the query-time disk caches.

The DB has an extractor staleness gate (ranking.py): when EXTRACTOR_VERSION
bumps, the DB is reset and rescanned. But the *query-time* disk caches were
keyed only by CACHE_VERSION:

1. The per-file tag disk cache (cache.py) stores get_tags() output AFTER
   _add_class_context_to_tags — i.e. the qualified names the extractor
   version exists to gate. After an extractor bump the gate fires, the
   rescan calls get_tags, the disk cache serves the STALE qualified tags
   (mtime unchanged), and the DB is re-stamped with the new extractor
   version. Permanent, undetectable staleness.

2. The cross-file import/call-graph bundle (graph.py) fingerprint includes
   CACHE_VERSION but not EXTRACTOR_VERSION; its defs carry the same
   class-context qualification, so a stale bundle survives extractor bumps.

Both caches must incorporate EXTRACTOR_VERSION.
"""
import tempfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from core import Tricorder
import cache as cache_mod
import graph as graph_mod
import database as database_mod
import ranking as ranking_mod

_QH = {'info': lambda *a: None, 'warning': lambda *a: None,
       'error': lambda *a: None}


def _repo(n=2):
    d = Path(tempfile.mkdtemp())
    for i in range(n):
        (d / f"f{i}.py").write_text(f"def func{i}():\n    return {i}\n")
    return d


def _cache_dir_for(root):
    stub = SimpleNamespace(root=Path(root).resolve(), cache_size_limit=2**30)
    return cache_mod.TagsCacheMixin._cache_dir(stub)


def test_tag_cache_dir_incorporates_extractor_version(tmp_path, monkeypatch):
    """Bumping EXTRACTOR_VERSION must move the per-file tag disk cache."""
    before = _cache_dir_for(tmp_path)
    monkeypatch.setattr(cache_mod, "EXTRACTOR_VERSION",
                        database_mod.EXTRACTOR_VERSION + 1, raising=False)
    after = _cache_dir_for(tmp_path)
    assert before != after, (
        "per-file tag disk cache ignores EXTRACTOR_VERSION: after a bump, "
        "a forced rescan would re-insert stale qualified tags from cache"
    )


def test_cross_ref_fingerprint_incorporates_extractor_version(tmp_path,
                                                              monkeypatch):
    """Bumping EXTRACTOR_VERSION must invalidate the cross-file bundle."""
    d = _repo(1)
    t = Tricorder(root=str(d), output_handler_funcs=_QH)
    try:
        before = t._cross_ref_fingerprint()
        monkeypatch.setattr(graph_mod, "EXTRACTOR_VERSION",
                            database_mod.EXTRACTOR_VERSION + 1, raising=False)
        after = t._cross_ref_fingerprint()
        assert before != after, (
            "cross-ref disk bundle fingerprint ignores EXTRACTOR_VERSION: "
            "stale qualified defs/refs would survive an extractor bump"
        )
    finally:
        t.close()


def test_extractor_bump_forces_reparse_not_cache_replay(monkeypatch):
    """End to end: after an extractor bump, the forced rescan must re-parse
    files instead of replaying stale qualified tags from the disk cache."""
    d = _repo(2)
    p = str(d / "idx.db")
    files = [str(d / "f0.py"), str(d / "f1.py")]

    t1 = Tricorder(root=str(d), db_path=p, output_handler_funcs=_QH)
    t1.get_ranked_tags([], files)  # populates the per-file disk tag cache
    t1.close()

    bumped = database_mod.EXTRACTOR_VERSION + 1
    monkeypatch.setattr(database_mod, "EXTRACTOR_VERSION", bumped)
    monkeypatch.setattr(ranking_mod, "EXTRACTOR_VERSION", bumped)
    monkeypatch.setattr(cache_mod, "EXTRACTOR_VERSION", bumped, raising=False)
    monkeypatch.setattr(graph_mod, "EXTRACTOR_VERSION", bumped, raising=False)

    calls = []
    orig = Tricorder.get_tags_raw
    def counting(self, fname, rel_fname):
        calls.append(fname)
        return orig(self, fname, rel_fname)
    monkeypatch.setattr(Tricorder, "get_tags_raw", counting)

    t2 = Tricorder(root=str(d), db_path=p, output_handler_funcs=_QH)
    try:
        t2.get_ranked_tags([], files)  # extractor gate fires -> full rescan
    finally:
        t2.close()

    assert len(calls) >= 2, (
        "extractor-bump rescan served tags from the disk cache instead of "
        "re-parsing: stale qualified names were re-inserted and re-stamped"
    )
    # And the DB now carries the bumped stamp (gate ran, not skipped).
    con = database_mod.sqlite3.connect(p)
    try:
        stamp = con.execute(
            "SELECT extractor_version FROM meta ORDER BY rowid DESC LIMIT 1"
        ).fetchone()[0]
    finally:
        con.close()
    assert stamp == bumped
