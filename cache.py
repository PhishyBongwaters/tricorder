"""
Per-file tags cache (diskcache) — extracted from core.py (SPEC_db_map Goal 2).

This module holds the existing per-file tags cache: the diskcache instance,
cache-dir identity, cache error recovery, and the get_tags() cache accessor.

Behavior-neutral refactor: method names and signatures are identical to what
lived on Tricorder, and Tricorder inherits this as a mixin
(`class Tricorder(TagsCacheMixin)`) so every caller (`tricorder.py`,
`tricorder_server.py`, plugins, bench, tests) keeps working unchanged.

Deliberately NOT moved here:
- get_tags_raw / _parse_with_timeout — the tree-sitter parser. Per SPEC the
  parser belongs to parser.py (a later goal), not cache.py; they stay on
  Tricorder and get_tags() calls them via `self`.
- discover_src_files — already lives in utils.py; not duplicated here.
"""

import os
import hashlib
import shutil
import sqlite3
from pathlib import Path
from typing import List

import diskcache

from utils import get_cache_root, Tag

CACHE_VERSION = 1

SQLITE_ERRORS = (sqlite3.OperationalError, sqlite3.DatabaseError)


class TagsCacheMixin:
    """Per-file tags cache (diskcache), mixed into Tricorder."""

    def _cache_dir(self) -> Path:
        """TC-003: store the persistent tags cache OUTSIDE the repository.

        A repo must not control security-sensitive cache state (stale reuse,
        poisoning, metadata contamination). Identity is derived from the
        resolved repo path + tricorder version + config hash, so distinct
        repos never share a cache and one repo can't poison another's.
        ponytail: ~/.tricorder/cache/<sha1(root|version|config)>.
        """
        # Canonical cache root -- falls back to home .tricorder/cache if the
        # explicit root is unavailable, preserving the existing fallback
        # behavior of load_tags_cache().
        _root = get_cache_root()
        if _root is not None:
            base = _root / "cache"
        else:
            base = Path(os.environ.get(
                "TRICORDER_CACHE_HOME",
                str(Path.home() / ".tricorder" / "cache"),
            ))
        key = f"{self.root.resolve()}|v{CACHE_VERSION}|{self.cache_size_limit}"
        h = hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]
        return base / h

    def load_tags_cache(self):
        """Load the persistent tags cache from outside the repo (TC-003)."""
        cache_dir = self._cache_dir()
        try:
            self.TAGS_CACHE = diskcache.Cache(
                str(cache_dir),
                size_limit=self.cache_size_limit,
                eviction_policy=self.cache_eviction_policy,
            )
        except Exception as e:
            # Fall back to in-memory cache — common on Windows with
            # read-only cache files from previous runs.
            self.output_handlers['warning'](
                f"Failed to initialize diskcache at {cache_dir}: {e}. "
                f"Falling back to in-memory cache (not persistent)."
            )
            self.TAGS_CACHE = {}

    def _make_writable(self, path: Path):
        """Try to make a file/directory writable on Windows."""
        try:
            import stat
            path.chmod(path.stat().st_mode | stat.S_IWRITE)
        except Exception:
            pass

    def tags_cache_error(self):
        """Handle tags cache errors."""
        try:
            cache_dir = self._cache_dir()
            if cache_dir.exists():
                # Make all files writable before removing
                for root, dirs, files in os.walk(cache_dir, topdown=False):
                    for name in files:
                        self._make_writable(Path(root) / name)
                    for name in dirs:
                        self._make_writable(Path(root) / name)
                self._make_writable(cache_dir)
                shutil.rmtree(cache_dir)
            self.load_tags_cache()
        except Exception:
            self.TAGS_CACHE = {}

    def get_tags(self, fname: str, rel_fname: str) -> List[Tag]:
        """Get tags for a file, using cache when possible."""
        # ponytail: skip files that can't have tree-sitter symbols — saves read+parse per file
        _SKIP_EXTS = {'.frag', '.vert', '.inc', '.icns', '.plist', '.entitlements',
                      '.cmake.in', '.h.in', '.cpp.in', '.hpp.in'}
        if Path(fname).suffix in _SKIP_EXTS or fname.endswith(('.cmake.in', '.h.in', '.cpp.in', '.hpp.in')):
            return []

        file_mtime = self.get_mtime(fname)
        if file_mtime is None:
            return []

        # Use lock to prevent TOCTOU race condition in check-then-write
        with self._tags_cache_lock:
            try:
                # Both diskcache.Cache and dict have .get() method
                cached_entry = self.TAGS_CACHE.get(fname)

                if cached_entry and cached_entry.get("mtime") == file_mtime:
                    try:
                        with open(os.path.join(self._cache_dir(), "hits.log"), "a") as _hf:
                            _hf.write(f"hit\tget_tags\t{fname}\n")
                    except Exception:
                        pass
                    return cached_entry["data"]
            except SQLITE_ERRORS:
                self.tags_cache_error()

            # Cache miss or file changed
            tags = self.get_tags_raw(fname, rel_fname)

            # Post-process tags to add class context to method names
            tags = self._add_class_context_to_tags(tags)

            try:
                self.TAGS_CACHE[fname] = {"mtime": file_mtime, "data": tags}
            except SQLITE_ERRORS:
                self.tags_cache_error()

            return tags