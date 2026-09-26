"""
Utility functions for Tricorder.
"""

import hashlib
import json
import os
import fnmatch
import re
import tempfile
import time
import sys
from pathlib import Path
from typing import Optional, List
from collections import namedtuple
from dataclasses import dataclass, asdict

# tiktoken is optional — only needed for count_tokens(). Imported lazily.
_tiktoken = None

# Tag namedtuple for storing parsed code definitions and references
Tag = namedtuple("Tag", "rel_fname fname line name kind".split())


# ---------------------------------------------------------------------------
# Canonical external cache root
# ---------------------------------------------------------------------------
# All persistent tricorder state (token-budget cache, ctags indexes,
# diskcache tags cache, plugin meta) lives under a single root so that
# the resolution logic, permission handling, and override mechanism are
# defined in exactly one place.
#
# Override: set TRICORDER_CACHE_HOME to relocate everything.
# Failure: if the root cannot be created, cache features are skipped and
# a warning is emitted once per process.  There is NO silent in-memory
# fallback -- a silent fallback hides cache corruption and makes it
# impossible to tell whether the feature is working.
# ---------------------------------------------------------------------------

_CACHE_ROOT: Optional[Path] = None


def get_cache_root() -> Path:
    """Return the canonical Tricorder cache root.

    The root is under the tricorder workspace by default so it is always
    writable from tests and CLI runs.  Override with TRICORDER_CACHE_HOME.
    """
    global _CACHE_ROOT

    if _CACHE_ROOT is not None:
        return _CACHE_ROOT

    base = Path(
        os.environ.get(
            "TRICORDER_CACHE_HOME",
            str(Path(__file__).resolve().parent / ".tricorder"),
        )
    ).resolve()

    base.mkdir(parents=True, exist_ok=True)
    _CACHE_ROOT = base
    return base


def resolve_or_none(path: str) -> Optional[str]:
    """Resolve a path, returning None when it cannot be resolved.

    Symlink loops raise RuntimeError from Path.resolve(); dangling
    links and permission errors raise OSError. Per-file call sites must
    skip such files with a warning instead of crashing the whole scan.
    """
    try:
        return str(Path(path).resolve())
    except (OSError, RuntimeError):
        return None


def stat_fingerprint(st) -> tuple:
    """(size, mtime_ns) stat fingerprint for change detection.

    mtime is kept at nanosecond resolution on purpose: truncating to
    whole seconds (int(st.st_mtime)) makes a same-second, same-size edit
    invisible to the dirty-diff, so incremental rescans and --diff would
    serve stale tags forever with no signal. SQLite INTEGER holds ns
    values fine (~1.8e18 < 9.2e18 max).
    DBs written by older versions store whole-second mtimes; those
    compare unequal to ns values, so the first scan after upgrade
    re-parses everything once (self-healing, no migration needed).
    """
    return (st.st_size, st.st_mtime_ns)


def read_only_connect(db_path: str):
    """Open a sqlite DB read-only; never creates the file.

    immutable=1 matters: every file DB uses WAL journal mode, and a
    plain mode=ro open of a WAL DB fails ("unable to open database
    file") when the -shm/-wal sidecars can't be created — exactly the
    read-only-checkout case these probes target. immutable=1 tells
    sqlite to read the main file only, skipping sidecar access (the
    caller must not need uncheckpointed WAL rows, and must hold the
    connection only briefly — the file is assumed frozen meanwhile).

    The path is percent-encoded into the URI (Path.as_uri) so DBs under
    directories containing '#' or '?' (e.g. Windows `C:\\dev\\proj#2\\`)
    open correctly instead of silently targeting a truncated path.
    """
    import sqlite3 as _sq
    uri = Path(os.path.abspath(db_path)).as_uri() + "?mode=ro&immutable=1"
    return _sq.connect(uri, uri=True)


def _db_writable(db_path: str) -> bool:
    """True when the process can write the DB file and its directory.

    SQLite needs the directory too (WAL -shm/-wal sidecars). A canonical
    DB that exists but isn't writable (read-only checkout, foreign owner)
    can't back a map scan — the extractor gate does DELETEs on first use.

    The directory check is a create+delete probe file, not
    os.access(dir, W_OK): on Windows os.access uses MSVC _waccess, which
    for directories checks existence only, never ACLs. The file check
    keeps os.access — it honors ACLs on files on Windows.
    """
    p = Path(db_path)
    if p.exists() and not os.access(str(p), os.W_OK):
        return False
    try:
        fd, probe = tempfile.mkstemp(dir=str(p.parent),
                                     prefix=".tricorder-wprobe-")
        try:
            os.close(fd)
        finally:
            os.unlink(probe)
        return True
    except OSError:
        return False


def db_root_matches(db_path: str, root: str) -> bool:
    """True when the DB's meta.root is the same directory as root.

    Canonical-DB lookup is by directory basename, so two repos that share a
    folder name collide in the shared cache dir. Serving the wrong repo's
    index would silently corrupt diff/detect/detail answers — a mismatched
    DB is treated as absent instead. Read-only; never creates the DB.
    """
    try:
        con = read_only_connect(db_path)
        try:
            row = con.execute(
                "SELECT root FROM meta ORDER BY rowid DESC LIMIT 1").fetchone()
        finally:
            con.close()
    except Exception:
        return False
    if not row or not row[0]:
        return False
    try:
        return (os.path.normcase(os.path.abspath(row[0]))
                == os.path.normcase(os.path.abspath(root)))
    except Exception:
        return False


def safe_write(path, text, *, allow_escape=False, encoding="utf-8") -> Path:
    """Write text to a Tricorder-managed path. Structural guard for the
    never-write-to-scanned-repo invariant (TC-006/TC-008).

    By default the resolved target must stay inside get_cache_root()
    (.tricorder workspace); an escape raises ValueError loud. The --output
    escape hatch passes allow_escape=True. I/O failures raise OSError so
    best-effort caches (budget/tags) can swallow only disk errors, not escapes.
    """
    target = Path(path).resolve()
    if not allow_escape:
        root = get_cache_root()
        if root not in target.parents:
            raise ValueError(
                f"safe_write blocked escape: {target} is outside cache root {root}"
            )
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding=encoding)
    return target


@dataclass
class SymbolRecord:
    """Symbol record for search_symbols MCP tool (Milestone 1).

    Flat JSON-serializable record representing a single code symbol
    extracted from tree-sitter AST data. No nested trees.
    """
    name: str
    type: str          # function | class | type | variable | method | import
    file: str          # absolute file path
    line: int          # start line number (1-indexed)
    end_line: int      # end line number (if available)
    signature: str     # function/method signature string
    docstring: str     # docstring content if present
    language: str      # file language (python, typescript, etc.)
    kind: str          # tree-sitter node kind string
    body: str = ""     # code body, first 500 chars (get_symbol_details)
    callers: list = None  # list of {file, line} dicts (get_symbol_details)
    callees: list = None  # list of {name, file, line} dicts (get_symbol_details)
    stop_note: str = ""  # set when name is a stop-name: cross-file callers
                         # intentionally unresolved (def in >50 files)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "SymbolRecord":
        return cls(**{k: d[k] for k in cls.__dataclass_fields__})


def count_tokens(text: str, model_name: str = "gpt-4") -> int:
    """Count tokens in text using tiktoken (lazy import)."""
    global _tiktoken
    if _tiktoken is None:
        try:
            import tiktoken as _tiktoken_mod
            _tiktoken = _tiktoken_mod
        except ImportError:
            raise RuntimeError("tiktoken is required for token counting. Install with: pip install tiktoken")
    if not text:
        return 0

    try:
        encoding = _tiktoken.encoding_for_model(model_name)
    except KeyError:
        # Fallback for unknown models
        encoding = _tiktoken.get_encoding("cl100k_base")

    return len(encoding.encode(text))


def enforce_search_budget(items, max_tokens):
    """Trim a ranked search-result list to a token budget (in place-safe).

    Trim order mirrors the detail budgetter: drop per-hit bulk first
    (`context`, else `docstring`) from the lowest-ranked hits upward, then
    drop lowest-ranked hits entirely. Identity (`file`/`line`/`name`) of
    the head hit always survives (best-effort under the floor, same
    convention as the detail budget).

    items: list of result dicts, best first. max_tokens None or <= 0
    disables trimming (current unbounded behavior).
    Returns (items, truncated, omitted) where omitted counts dropped hits
    (context-stripped survivors are still listed, not omitted).
    """
    if not items:
        return items, False, 0
    if max_tokens is None or max_tokens <= 0:
        return items, False, 0

    def _cost(rs):
        return count_tokens(json.dumps(rs), "gpt-4")

    original = len(items)
    out = [dict(h) for h in items]
    truncated = False
    if _cost(out) <= max_tokens:
        return out, False, 0

    # Phase 1: strip bulk text tail-up (context for detect hits,
    # docstring for symbol records).
    for h in reversed(out):
        if _cost(out) <= max_tokens:
            break
        for key in ("context", "docstring"):
            if h.get(key):
                h[key] = ""
                truncated = True
                break

    # Phase 2: drop tail hits until the serialized total holds or one
    # identity hit remains (measured each step — tokenizers aren't
    # additive across edits, so the loop itself is the guarantee).
    while len(out) > 1 and _cost(out) > max_tokens:
        out.pop()
        truncated = True

    return out, True, original - len(out)


def read_text(filename: str, encoding: str = "utf-8", silent: bool = False, 
              strict: bool = False) -> Optional[str]:
    """Read text from file with error handling.
    
    Args:
        filename: Path to file
        encoding: Text encoding (default: utf-8)
        silent: If True, suppress error messages
        strict: If True, raise UnicodeError on decode failure instead of
                silently dropping invalid bytes (errors='ignore').
                Default False preserves backward compatibility.
    
    Returns:
        File contents as string, or None on error.
    
    Note:
        Default behavior (strict=False) uses errors='ignore' which silently
        drops invalid bytes. This is intentional for source code indexing
        where mixed-encoding repos are common. Use strict=True for
        validation pipelines.
    """
    errors = 'strict' if strict else 'ignore'
    try:
        return Path(filename).read_text(encoding=encoding, errors=errors)
    except FileNotFoundError:
        if not silent:
            print(f"Error: {filename} not found.")
        return None
    except IsADirectoryError:
        if not silent:
            print(f"Error: {filename} is a directory.")
        return None
    except OSError as e:
        if not silent:
            print(f"Error reading {filename}: {e}")
        return None
    except UnicodeError as e:
        if not silent:
            print(f"Error decoding {filename}: {e}")
        return None
    except Exception as e:
        if not silent:
            print(f"An unexpected error occurred while reading {filename}: {e}")
        return None


_SKIP_EXTS = {'.frag', '.vert', '.inc', '.icns', '.plist', '.entitlements',
              '.cmake.in', '.h.in', '.cpp.in', '.hpp.in'}
_BINARY_MEDIA_EXTS = {
    '.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp', '.ico', '.tif', '.tiff',
    '.mp4', '.mov', '.mkv', '.avi', '.webm', '.mp3', '.wav', '.flac', '.ogg',
    '.pdf', '.svg',
}
# Archive/compressed formats — not source code, never wants to be in a code map.
_ARCHIVE_EXTS = {
    '.tar', '.gz', '.zip', '.bz2', '.xz', '.7z', '.rar', '.tgz', '.tbz2',
    '.db', '.sqlite', '.sqlite3', '.db3',  # SQLite database files
}
# Data/asset text formats — not source code, never wants to be in a code map.
_DATA_EXTS = {
    '.milk',          # projectM presets
    '.json', '.xml', '.yaml', '.yml', '.toml', '.ini', '.cfg', '.config',
    '.csv', '.tsv',
    '.md', '.txt', '.rst',  # Documentation, not source code
}
# Minified/bundled third-party artifacts — vendored code under a filename
# disguise (jquery-4.0.0.slim.js etc.). Skipped at discovery so they never
# enter tags/refs/ranks or MAP/T1 payloads. ctags path already excludes
# *.min.js/*.min.css; the DB scan path needs the same (plus slim/bundle).
_MINIFIED_SUFFIXES = {
    '.min.js', '.min.css', '.slim.js', '.bundle.js',
}
# T1 (SPEC-minified-fixture-exclusion): fixture/testdata subtrees hold
# minified blobs and gzipped fixtures (e.g. Rails
# actionpack/test/fixtures/public/gzip/application-<hash>.js) that parse
# into hundreds of fake cross-referencing symbols — a PageRank bomb. Skip
# at discovery so they never enter tags/refs/ranks/MAP. Deprioritize,
# never exclude, is NOT the rule here: these are never real source.
# Additive to _MINIFIED_SUFFIXES (whose semantics are unchanged).
_FIXTURE_SKIP_DIRS = {'fixtures', '__fixtures__', 'testdata'}
# Rails asset fingerprinting / webpack contenthash: <name>-<hexhash>.js/css
# (e.g. application-a71b3024f80aea3181c09774ca17e712.js). Lowercase-hex,
# 8-64 chars so short suffixes (my-app-v2.js) never match. Matched against
# the lowercased basename.
_HASH_ASSET_RE = re.compile(r'-[0-9a-f]{8,64}\.(js|css)$')


def _is_fixture_or_hash_asset(rel_posix: str, basename_lower: str) -> bool:
    """T1 discovery-time decision: fixture subtree or fingerprinted asset.

    rel_posix: path relative to scan root, POSIX-normalized. Any path
    segment in _FIXTURE_SKIP_DIRS → skip. Otherwise the basename is
    tested against _HASH_ASSET_RE. Deterministic, stdlib-only.
    """
    for seg in rel_posix.split('/'):
        if seg.lower() in _FIXTURE_SKIP_DIRS:
            return True
    return _HASH_ASSET_RE.search(basename_lower) is not None


# T1 mechanism 2 (SPEC-minified-fixture-exclusion): minified-blob content
# sniff. Name rules (mechanisms 1+3) cannot catch a minified lib living
# at a normal path (Rails guides/assets/.../clipboard.js headed the MAP
# after the fixture purge). Measured on the Rails tree (64 .js/.css):
# the blob's longest line is 10,361 chars at mean 1,307; real shipped
# bundles peak at longest 1,473 / mean 48. BOTH signals must fire, so a
# real file with one long line but low mean (activestorage.js shape)
# survives. .js/.css only (minified blobs live there); bounded 64KB
# head read; unreadable files are kept (fail-open: exclusion needs
# positive evidence).
_SNIFF_BYTES = 65536
_SNIFF_MIN_LONGEST_LINE = 2000
_SNIFF_MIN_MEAN_LINE = 500
_SNIFF_EXTS = {'.js', '.css'}


def _is_minified_blob(full_path: str, basename_lower: str) -> bool:
    """T1 discovery-time decision: minified blob by content shape."""
    if not any(basename_lower.endswith(ext) for ext in _SNIFF_EXTS):
        return False
    try:
        if os.path.getsize(full_path) <= _SNIFF_MIN_LONGEST_LINE:
            return False
        with open(full_path, 'rb') as f:
            head = f.read(_SNIFF_BYTES)
    except OSError:
        return False
    text = head.decode('utf-8', errors='replace')
    lines = text.split('\n')
    if not lines:
        return False
    if max(len(L) for L in lines) <= _SNIFF_MIN_LONGEST_LINE:
        return False
    return (len(text) / len(lines)) > _SNIFF_MIN_MEAN_LINE
# Skip files larger than this (bytes) — likely generated/binary/not source.
# Overridable via env TRICORDER_MAX_SOURCE_FILE_SIZE (bytes). Read at call time
# (see _env_int/_env_float) so tests and runtime tuning don't require re-import.
_MAX_SOURCE_FILE_SIZE = 1024 * 1024
_MAX_SCAN_FILES = 0  # 0 = unlimited; env TRICORDER_MAX_SCAN_FILES to cap
# TC-002: missing envelope pieces — directory-depth, total-byte, and scan-time
# budgets so a hostile repo can't drive unbounded CPU/memory/disk. All
# overridable via env; discovery early-stops at _MAX_SCAN_FILES only when set
# (0 = unlimited by default so full-repo maps are never truncated).
_MAX_SCAN_DEPTH = 25
_MAX_TOTAL_BYTES = 0  # 0 = unlimited; env TRICORDER_MAX_TOTAL_BYTES to cap
_MAX_SCAN_TIME_S = 0.0  # 0 = unlimited; env TRICORDER_MAX_SCAN_TIME_S to cap
_BUILTIN_SKIP_DIRS = {'node_modules', '__pycache__', 'venv', 'env', 'build', 'dist', '.tox', '.eggs'}


def _env_int(name: str, default: int) -> int:
    """Read an int env override at call time (TC-002 live tuning).
    If env is set to '0' or a negative number, returns it (0 = unlimited).
    If unset, returns default.
    """
    val = os.environ.get(name)
    if val is not None:
        try:
            return int(val)
        except (TypeError, ValueError):
            pass
    return default


def _env_float(name: str, default: float) -> float:
    val = os.environ.get(name)
    if val is not None:
        try:
            return float(val)
        except (TypeError, ValueError):
            pass
    return default


def _discover_src_files_threaded(directory, skip_dirs, exclude_globs, report,
                                 workers, max_scan_depth, max_total_bytes,
                                 max_scan_files, max_scan_time_s,
                                 max_source_file_size, root_depth, start):
    """Bounded-pool directory walk. Same filters/budgets as the serial path.

    Controls: fixed worker count, one lock around budget counters, stop
    flag checked per directory, reservations made before appends (budgets
    can never overshoot), output sorted for determinism.
    """
    import queue as _queue
    import threading as _threading

    if report is not None:
        report.clear()
    lock = _threading.Lock()
    stop = {"reason": None}
    # state: files, total_bytes, oversized_skipped, depth_skipped, pending
    st = {"files": [], "bytes": 0, "oversized": 0, "depth": 0, "pending": 1}
    q: _queue.Queue = _queue.Queue()
    _root_resolved = str(Path(directory).resolve())
    q.put(_root_resolved)

    def process_dir(d):
        try:
            entries = list(os.scandir(d))
        except OSError:
            return []
        depth = len(Path(d).parts) - root_depth
        subdirs = []
        if depth <= max_scan_depth:
            for e in entries:
                try:
                    if not e.is_dir(follow_symlinks=False):
                        continue
                except OSError:
                    continue
                if e.name.startswith('.') or e.name in skip_dirs:
                    continue
                if depth + 1 > max_scan_depth:
                    with lock:
                        st["depth"] += 1
                    continue
                subdirs.append(e.path)
        else:
            with lock:
                st["depth"] += len([e for e in entries
                                    if e.is_dir(follow_symlinks=False)])
        for e in entries:
            if stop["reason"]:
                return subdirs
            try:
                if e.is_dir(follow_symlinks=False) or e.name.startswith('.'):
                    continue
            except OSError:
                continue
            low = e.name.lower()
            if any(low.endswith(ext) for ext in _SKIP_EXTS | _BINARY_MEDIA_EXTS | _ARCHIVE_EXTS | _DATA_EXTS | _MINIFIED_SUFFIXES):
                continue
            # T1: fixture subtree remnants (rel-path belt-and-braces;
            # dir pruning via skip_dirs handles the common case) and
            # fingerprinted asset blobs never enter the map.
            try:
                _rel = os.path.relpath(e.path, directory).replace(os.sep, '/')
            except ValueError:
                continue
            if _is_fixture_or_hash_asset(_rel, low):
                continue
            try:
                sz = e.stat(follow_symlinks=False).st_size
            except OSError:
                sz = 0
            if sz > max_source_file_size:
                with lock:
                    st["oversized"] += 1
                continue
            # T1 mechanism 2: minified-blob content sniff (.js/.css only).
            if _is_minified_blob(e.path, low):
                continue
            if exclude_globs:
                try:
                    rel = os.path.relpath(e.path, directory).replace(os.sep, '/')
                    if any(fnmatch.fnmatch(rel, pat) for pat in exclude_globs):
                        continue
                except ValueError:
                    continue
            with lock:
                if stop["reason"]:
                    return subdirs
                if max_scan_files > 0 and len(st["files"]) >= max_scan_files:
                    stop["reason"] = f"reached file-count limit ({max_scan_files})"
                    return subdirs
                if max_total_bytes > 0 and st["bytes"] + sz >= max_total_bytes:
                    stop["reason"] = f"reached total-byte limit ({max_total_bytes} bytes)"
                    return subdirs
                if max_scan_time_s > 0 and (time.monotonic() - start) >= max_scan_time_s:
                    stop["reason"] = f"reached scan-time limit ({max_scan_time_s}s)"
                    return subdirs
                # Emit in serial-path format (os.path.join off the as-given
                # root) so threaded/serial runs are byte-identical inputs
                # downstream — DB rel keys and cap prefixes must not shift.
                st["files"].append(os.path.join(
                    directory, os.path.relpath(e.path, _root_resolved)))
                st["bytes"] += sz
        return subdirs

    def worker():
        while True:
            if stop["reason"]:
                # Drain without processing; pending handled by main loop below.
                try:
                    d = q.get(timeout=0.1)
                except _queue.Empty:
                    return
                if d is None:
                    q.task_done()
                    return
                with lock:
                    st["pending"] -= 1
                    if st["pending"] == 0:
                        for _ in range(workers):
                            q.put(None)
                q.task_done()
                continue
            try:
                d = q.get(timeout=0.5)
            except _queue.Empty:
                with lock:
                    if st["pending"] == 0:
                        return
                continue
            if d is None:
                q.task_done()
                return
            for sub in process_dir(d):
                q.put(sub)
                with lock:
                    st["pending"] += 1
            with lock:
                st["pending"] -= 1
                if st["pending"] == 0:
                    for _ in range(workers):
                        q.put(None)
            q.task_done()

    threads = [_threading.Thread(target=worker, daemon=True) for _ in range(workers)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    files = sorted(st["files"])
    if report is not None:
        report["files_considered"] = len(files)
        report["oversized_skipped"] = st["oversized"]
        report["depth_skipped"] = st["depth"]
        if stop["reason"]:
            report["warning"] = (
                f"Scan completed with limits: skipped {st['oversized']} "
                f"oversized files, {st['depth']} files beyond depth "
                f"{max_scan_depth}; {stop['reason']}."
            )
    return files


def discover_src_files(directory: str, use_gitignore: bool = True, exclude_globs: Optional[List[str]] = None, report: Optional[dict] = None) -> List[str]:
    """Walk a directory and return source files, skipping noise.

    Shared by tricorder_server.find_src_files and Tricorder._discover_files.
    ponytail: one implementation, two callers — no drift.

    TC-002 resource envelope: a single global budget bounds the walk so a
    hostile repo can't drive unbounded CPU/memory/disk. Files are skipped (not
    silently truncated) when they breach a single-file cap, and the walk stops
    cleanly when it hits the file-count / total-byte / directory-depth / time
    limits. If `report` is provided, it is populated with a human-readable
    partial-scan warning instead of raising.

    exclude_globs: optional list of glob patterns matched against the path
    is POSIX-normalized, relative to `directory`. Excludes third-party/
    vendored subtrees from ranking, e.g. exclude_globs=["vendor/**"].
    """
    if report is not None:
        report.clear()
    if not os.path.isdir(directory):
        return [directory] if os.path.isfile(directory) else []
    # Find git root for .gitignore parsing
    gitignore_dirs: set = set()
    if use_gitignore:
        git_root = None
        p = Path(directory).resolve()
        while p != p.parent:
            if (p / '.git').exists():
                git_root = str(p)
                break
            p = p.parent
        gitignore_dirs = parse_gitignore(git_root or directory)
    skip_dirs = gitignore_dirs | _BUILTIN_SKIP_DIRS | {'vendor'} | _FIXTURE_SKIP_DIRS
    # TC-002: read envelope budgets at call time so env overrides (incl. tests) work.
    max_scan_depth = _env_int("TRICORDER_MAX_SCAN_DEPTH", _MAX_SCAN_DEPTH)
    max_total_bytes = _env_int("TRICORDER_MAX_TOTAL_BYTES", _MAX_TOTAL_BYTES)
    max_scan_files = _env_int("TRICORDER_MAX_SCAN_FILES", _MAX_SCAN_FILES)
    max_scan_time_s = _env_float("TRICORDER_MAX_SCAN_TIME_S", _MAX_SCAN_TIME_S)
    max_source_file_size = _env_int("TRICORDER_MAX_SOURCE_FILE_SIZE", _MAX_SOURCE_FILE_SIZE)
    start = time.monotonic()
    root_depth = Path(directory).resolve().parts.__len__()
    # Threaded walk: directory listing on Windows is latency-bound, so a
    # small bounded pool beats a serial walk 3-5x. Controls against flood:
    # fixed worker count (env TRICORDER_WALK_WORKERS, default min(8, cpu)),
    # one shared lock for budget counters + stop flag, deterministic sorted
    # output. 0/1 = serial legacy path.
    import concurrent.futures as _cf
    try:
        _workers = int(os.environ.get("TRICORDER_WALK_WORKERS", "0"))
    except ValueError:
        _workers = 0
    if _workers <= 0:
        _workers = min(8, os.cpu_count() or 4)
    if _workers > 1:
        return _discover_src_files_threaded(
            directory, skip_dirs, exclude_globs, report, _workers,
            max_scan_depth, max_total_bytes, max_scan_files,
            max_scan_time_s, max_source_file_size, root_depth, start,
        )
    src_files = []
    total_bytes = 0
    oversized_skipped = 0
    depth_skipped = 0
    for r, d, f_list in os.walk(directory):
        # TC-002: directory-depth budget.
        depth = Path(r).resolve().parts.__len__() - root_depth
        if depth > max_scan_depth:
            depth_skipped += len(d)
            d[:] = []
            continue
        d[:] = [dn for dn in d if not dn.startswith('.') and dn not in skip_dirs
                and (Path(r).resolve().parts.__len__() - root_depth + 1) <= max_scan_depth]
        for f in f_list:
            if f.startswith('.'):
                continue
            # Case-insensitive ext check: .Jpg slides past .jpg otherwise.
            low = f.lower()
            if any(low.endswith(ext) for ext in _SKIP_EXTS | _BINARY_MEDIA_EXTS | _ARCHIVE_EXTS | _DATA_EXTS | _MINIFIED_SUFFIXES):
                continue
            # T1: fingerprinted asset blob check (fixture subtrees are
            # pruned via skip_dirs above; the rel-segment check covers
            # the rest, e.g. a root itself named fixtures/).
            try:
                _rel = os.path.relpath(os.path.join(r, f), directory).replace(os.sep, '/')
            except ValueError:
                continue
            if _is_fixture_or_hash_asset(_rel, low):
                continue
            full = os.path.join(r, f)
            # Skip large files (likely generated/binary/not source)
            try:
                sz = os.path.getsize(full)
            except OSError:
                sz = 0
            if sz > max_source_file_size:
                oversized_skipped += 1
                continue
            # T1 mechanism 2: minified-blob content sniff (.js/.css only).
            if _is_minified_blob(full, low):
                continue
            if exclude_globs:
                try:
                    rel = os.path.relpath(full, directory).replace(os.sep, '/')
                    if any(fnmatch.fnmatch(rel, pat) for pat in exclude_globs):
                        continue
                except ValueError:
                    continue
            src_files.append(full)
            total_bytes += sz
            # TC-002: total-byte + file-count + scan-time budgets. Return a
            # clean partial result with a warning rather than failing
            # unpredictably. The pre-index probe is required to go deeper.
            hit_limit = None
            if max_scan_files > 0 and len(src_files) >= max_scan_files:
                hit_limit = f"reached file-count limit ({max_scan_files})"
            elif max_total_bytes > 0 and total_bytes >= max_total_bytes:
                hit_limit = f"reached total-byte limit ({max_total_bytes} bytes)"
            elif max_scan_time_s > 0 and (time.monotonic() - start) >= max_scan_time_s:
                hit_limit = f"reached scan-time limit ({max_scan_time_s}s)"
            if hit_limit:
                if report is not None:
                    report["warning"] = (
                        f"Scan completed with limits: skipped {oversized_skipped} "
                        f"oversized files, {depth_skipped} files beyond depth "
                        f"{max_scan_depth}; {hit_limit}."
                    )
                    report["files_considered"] = len(src_files)
                    report["oversized_skipped"] = oversized_skipped
                    report["depth_skipped"] = depth_skipped
                return src_files
    # Deterministic order: window stability across runs requires the walk
    # prefix to be stable, so the serial path sorts like the threaded one.
    src_files.sort()
    if report is not None:
        report["files_considered"] = len(src_files)
        report["oversized_skipped"] = oversized_skipped
        report["depth_skipped"] = depth_skipped
    return src_files


def parse_gitignore(root: str) -> set:
    """Parse .gitignore from repo root and return a set of directory patterns to skip.

    Handles: bare dir names (match any depth), trailing slashes, negation (!),
    comments, and blank lines. Does NOT handle complex fnmatch edge cases
    (leading slashes, double-asterisks, anchored paths, full negation semantics).

    SUPPORTED SUBSET (common 99%):
    - Directory names: "build", "dist", ".venv", "node_modules", "target"
    - Trailing slashes: "build/", "dist/"
    - Comments: "# comment"
    - Blank lines: skipped
    - Negation lines ("!pattern"): skipped entirely (not implemented)

    NOT SUPPORTED:
    - Anchored paths: "/build" (root-only)
    - Glob patterns: "*.log", "build/**", "**/temp"
    - Negation: "!build/keep_this"
    - Character classes: "build[0-9]"

    For full gitignore semantics, use a library like `pathspec` or `gitignore-parser`.

    ponytail: returns a set of directory basenames. os.walk filters dirs[:]
    against this set. If a pattern is file-only (e.g. '*.log'), it's ignored
    here — file-level filtering is handled by _SKIP_EXTS.
    """
    patterns: set[str] = set()
    gitignore = Path(root) / ".gitignore"
    if not gitignore.exists():
        return patterns
    try:
        for line in gitignore.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            # Negation: skip the pattern
            if line.startswith("!"):
                continue
            # Strip trailing slash (dir indicator)
            pattern = line.rstrip("/")
            # Only care about directory-level patterns (no dots, no wildcards)
            # — these are the common build dirs like "build", "dist", ".venv"
            if not pattern or "*" in pattern or "." in pattern:
                continue
            patterns.add(pattern)
    except OSError:
        pass
    return patterns


def detect_lang(fname: str) -> Optional[str]:
    """Detect language for a source file, overriding .h to cpp.

    grep-ast maps .h -> c, but most modern .h files are C++ (classes,
    namespaces, templates). The cpp tree-sitter grammar is a strict
    superset of C — it parses C code fine and the cpp query file has
    all the C patterns plus class/method patterns.

    ponytail: always map .h to cpp. Ceiling: a pure-C project's .h
    files would be parsed with the cpp query — harmless, the C
    patterns (struct, function, enum, typedef) are all in cpp-tags.scm.
    """
    from grep_ast import filename_to_lang
    # Local extension table, checked BEFORE grep-ast: grammars the pack
    # ships but filename_to_lang doesn't map. Colliding extensions
    # (.fs forth/fsharp, .v verilog/V, .m matlab/objc) stay unmapped
    # here — ambiguity needs content sniffing, not a coin flip.
    _LOCAL_EXTS = {
        ".nim": "nim", ".nims": "nim",
        ".vb": "vb",
        ".mojo": "mojo",
        ".cr": "crystal",
        ".awk": "awk",
        ".pyx": "cython", ".pxd": "cython",
        ".st": "smalltalk",
        ".sml": "sml",
        ".vala": "vala", ".vapi": "vala",
        ".graphql": "graphql", ".gql": "graphql",
        ".lean": "lean",
        ".ql": "ql", ".qll": "ql",
        ".wast": "wast", ".wat": "wat",
        ".fsi": "fsharp", ".fsx": "fsharp",
        ".mo": "motoko",
        ".re": "reason", ".rei": "reason",
        ".res": "rescript",
        ".sw": "sway",
        ".tact": "tact",
        ".yang": "yang",
        ".yul": "yul",
    }
    for ext, lang in _LOCAL_EXTS.items():
        if fname.endswith(ext):
            return lang
    lang = filename_to_lang(fname)
    if lang == "c" and fname.endswith((".h", ".H")):
        return "cpp"
    return lang


def _get_budget_cache_path(project_root: str) -> Optional[Path]:
    """Get path to budget cache file for a project.

    Returns None if the external cache root is unavailable.  Callers MUST
    check for None and degrade cleanly -- there is no silent fallback.
    """
    cache_root = get_cache_root()
    if cache_root is None:
        return None
    repo_hash = hashlib.sha256(Path(project_root).resolve().as_posix().encode()).hexdigest()[:16]
    cache_dir = cache_root / "cache" / repo_hash
    try:
        cache_dir.mkdir(parents=True, exist_ok=True)
    except (PermissionError, OSError):
        # Root was writable on first call but a sub-path became blocked
        return None
    return cache_dir / "budget.json"


def _get_budget_cache_key(model_name: str, exclude_globs: Optional[List[str]]) -> str:
    """Generate a cache key from model and exclude patterns."""
    key_data = model_name + "|" + "|".join(sorted(exclude_globs or []))
    return hashlib.sha256(key_data.encode()).hexdigest()[:16]


def calculate_full_repo_budget(project_root: str, token_estimate: int,
                               model_name: str = "gpt-4",
                               exclude_globs: Optional[List[str]] = None,
                               coverage_pct: Optional[float] = None,
                               force_refresh: bool = False) -> dict:
    """Calculate full repo budget (EXPENSIVE — reads and tokenizes ALL source files).

    This function tokenizes every discoverable source file in the repository.
    For large repos (Linux kernel, etc.) this can take seconds to minutes.
    Results are cached in .tricorder/cache/budget.json keyed by model + exclude_globs.

    Use sparingly. For hot paths, call once and reuse the full_repo_estimate.

    Args:
        project_root: Repository root path
        token_estimate: Estimated tokens of the map/output being compared
        model_name: Model name for tokenization (default: gpt-4)
        exclude_globs: Glob patterns to exclude from file discovery
        coverage_pct: Optional coverage percentage to include in result
        force_refresh: Skip cache and recalculate

    Returns: {"token_estimate": int, "full_repo_estimate": int,
              "savings_pct": float, "coverage_pct": float (optional)}
    """
    cache_path = _get_budget_cache_path(project_root)
    cache_key = _get_budget_cache_key(model_name, exclude_globs)

    # Try to load cached full_repo_estimate (cache_path may be None if cache
    # directory can't be created, e.g. permission denied or sandbox)
    cached_full = None
    if not force_refresh and cache_path and cache_path.exists():
        try:
            cached = json.loads(cache_path.read_text(encoding="utf-8"))
            cached_full = cached.get(cache_key)
        except Exception:
            pass

    # Calculate if not cached or forced
    if cached_full is None:
        files = discover_src_files(project_root, use_gitignore=True,
                                   exclude_globs=exclude_globs)
        full = 0
        for f in files:
            try:
                txt = read_text(f, silent=True)
                if txt:
                    full += count_tokens(txt, model_name)
            except Exception:
                continue

        # Cache the full estimate (skip if cache_path is None)
        if cache_path:
            try:
                cached = {}
                if cache_path.exists():
                    cached = json.loads(cache_path.read_text(encoding="utf-8"))
                cached[cache_key] = full
                safe_write(cache_path, json.dumps(cached))
            except OSError:
                pass  # best-effort cache; escapes still raise ValueError
        cached_full = full

    full = cached_full
    if not full or token_estimate <= 0:
        savings = 0.0
    else:
        savings = round(max(0.0, 1 - token_estimate / full) * 100, 1)

    result = {
        "token_estimate": int(token_estimate),
        "full_repo_estimate": int(full),
        "savings_pct": savings,
    }
    if coverage_pct is not None:
        result["coverage_pct"] = round(coverage_pct, 1)
    return result


# =============================================================================
# Scaled map budget: default map size grows with repo size, floored at 2048.
# Explicit budgets always win — this applies only when the caller passes
# nothing (CLI --map-tokens unset, MCP token_limit None).
# =============================================================================
# Mandated minimum map budget. Raisable via TRICORDER_MAP_BUDGET_FLOOR,
# never lowerable: the floor clamps upward only.
MAP_BUDGET_FLOOR = 2048

# Default tokens-per-file ratio. 0.5 approximates the historical 8192 default
# at Go scale (~16k files -> ~8k); retune via TRICORDER_MAP_BUDGET_RATIO.
MAP_BUDGET_RATIO = 0.5

# Smart MAP file threshold (v1.6): probe + ONE exact detect + conditional
# MAP applies to repos under this many files; larger repos go straight to
# MAP. Single source of truth for CLI --smart-map and MCP smart_map.
SMART_MAP_MAX_FILES = 5000

# Smart-map identifier-first (T2, SPEC-smartmap-identifier-first): rung 1
# receives the raw NL question, which can never exact-hit, so the v1.6
# single-probe skip never fired. Derive identifier candidates IN ORDER
# (backticked spans, then bare identifier tokens) and probe each as an
# exact detect; the first exact hit skips MAP exactly as today. The skip
# BAR never moves (quality=="exact" only) — only what gets tried widens.
# At most this many candidates are probed so the skip path stays an order
# of magnitude cheaper than the MAP it avoids.
SMART_MAP_MAX_CANDIDATES = 3

_BACKTICK_SPAN_RE = re.compile(r'`([^`\n]+)`')
_IDENT_TOKEN_RE = re.compile(
    r'[_A-Za-z][_0-9A-Za-z]*'
    r'(?:::[_A-Za-z][_0-9A-Za-z]*)*'
    r'(?:\.[_A-Za-z][_0-9A-Za-z]*)*'
)


def _clean_backticked(span: str) -> str:
    """Strip author-markup residue so `has_many()` probes as has_many."""
    s = span.strip().strip('()[]{}.,;:!?\'" \t')
    if s.lower().endswith('()'):
        s = s[:-2].rstrip()
    return s


def _is_candidate_shape(s: str) -> bool:
    if not s:
        return False
    return bool(re.fullmatch(
        r'[_A-Za-z][_0-9A-Za-z]*(?:::[_A-Za-z][_0-9A-Za-z]*)*'
        r'(?:\.[_A-Za-z][_0-9A-Za-z]*)*', s))


def smart_map_candidates(query: str,
                         max_candidates: int = SMART_MAP_MAX_CANDIDATES
                         ) -> list:
    """Identifier candidates for the smart-map skip probes, in try order.

    1. Backticked spans (author-marked, highest signal; kept even when
       short — an exact hit on an author-named symbol is a true hit).
    2. Bare Class::method / Class.method / snake_case / camelCase tokens
       in textual order (length >= 3, CODE + NL stopwords excluded —
       the SPEC names the CODE set; the NL set is required by the same
       SPEC's conservative constraint so filler like "the"/"what" can
       never become a skip probe). Scoped/dotted tokens also yield their
       tail component (the full form is tried first; tag names carry
       `::` qualification but not `.`).

    Deterministic, stdlib-only. Bounded by max_candidates (<= 0 = none).
    """
    if not query or max_candidates <= 0:
        return []
    cands: list = []
    seen = set()

    def _emit(s: str):
        key = s.lower()
        if not s or key in seen:
            return
        if len(cands) >= max_candidates:
            return
        seen.add(key)
        cands.append(s)

    # 1. Backticked spans — author-marked; no stopword/length filter (an
    # exact hit after author marking is definitionally signal).
    for m in _BACKTICK_SPAN_RE.finditer(query):
        if len(cands) >= max_candidates:
            break
        s = _clean_backticked(m.group(1))
        if _is_candidate_shape(s):
            _emit(s)
    # 2. Bare identifier tokens in textual order.
    for m in _IDENT_TOKEN_RE.finditer(query):
        if len(cands) >= max_candidates:
            break
        tok = m.group(0)
        if (len(tok) < 3 or tok.lower() in CODE_QUERY_STOPWORDS
                or tok.lower() in NL_QUERY_STOPWORDS):
            continue
        _emit(tok)
        # Tail component for scoped/dotted forms (counts toward the cap).
        if '::' in tok or '.' in tok:
            tail = re.split(r'::|\.', tok)[-1]
            if (len(cands) < max_candidates and len(tail) >= 3
                    and tail.lower() not in CODE_QUERY_STOPWORDS
                    and tail.lower() not in NL_QUERY_STOPWORDS
                    and _is_candidate_shape(tail)):
                _emit(tail)
    return cands


def smart_map_exact_hit(search_fn, query: str, max_results: int = 5,
                        max_candidates: int = SMART_MAP_MAX_CANDIDATES):
    """Run the T2 skip probes. search_fn(cand, max_results) -> (results,
    rescue_flag) — pass a lambda over Tricorder.search_identifiers with
    search_mode="exact".

    Returns (exact_hits, candidates_tried): the first candidate whose
    probe yields quality=="exact" hits wins (skip MAP as today);
    ([], tried) otherwise (today's MAP fallthrough, byte-for-byte).
    """
    tried: list = []
    for cand in smart_map_candidates(query, max_candidates):
        tried.append(cand)
        results, _rescue = search_fn(cand, max_results)
        exact = [r for r in results or [] if r.get("quality") == "exact"]
        if exact:
            return exact, tried
    return [], tried


def default_map_budget(n_files: int) -> int:
    """Map token budget for a repo of n_files when no explicit budget given.

    max(floor, ceil(n_files * ratio)). n_files <= 0 gets the floor.
    """
    try:
        floor = int(os.environ.get("TRICORDER_MAP_BUDGET_FLOOR",
                                   str(MAP_BUDGET_FLOOR)))
    except ValueError:
        floor = MAP_BUDGET_FLOOR
    floor = max(MAP_BUDGET_FLOOR, floor)
    try:
        ratio = float(os.environ.get("TRICORDER_MAP_BUDGET_RATIO",
                                     str(MAP_BUDGET_RATIO)))
    except ValueError:
        ratio = MAP_BUDGET_RATIO
    if ratio < 0:
        ratio = MAP_BUDGET_RATIO
    import math
    scaled = math.ceil(max(0, n_files) * ratio)
    return max(floor, scaled)


def repo_budget(project_root: str, token_estimate: int,
                model_name: str = "gpt-4",
                exclude_globs: Optional[List[str]] = None,
                coverage_pct: Optional[float] = None) -> dict:
    """Budget fields shared by CLI, MCP, and plugin (cached wrapper).

    NOTE: This reads/tokenizes the entire repo on FIRST call per project/model/exclude combo.
    Subsequent calls use cached full_repo_estimate from .tricorder/cache/budget.json.

    For hot paths where you already have full_repo_estimate, prefer constructing
    the budget dict manually to avoid any filesystem I/O.
    """
    return calculate_full_repo_budget(project_root, token_estimate, model_name,
                                       exclude_globs, coverage_pct, force_refresh=False)


# =============================================================================
# Turn-0 probe digest (shared by CLI --probe-digest, Hermes plugin, DSH plugin)
# =============================================================================
# A cheap navigation probe: language tally + rough size. NO map build, NO token
# budget (repo_budget reads/tokenizes every source file — too slow for turn 0
# on a kernel-scale tree). Designed so Hermes and DSH inject byte-identical
# turn-0 content from this one code path.

INJECT_MIN_FILES = 0  # gate removed — probe always injected if code files exist

CODE_EXTENSIONS = {
    ".py": "python", ".rs": "rust", ".c": "c", ".h": "cpp", ".cpp": "cpp",
    ".cc": "cpp", ".cxx": "cpp", ".hpp": "cpp", ".hxx": "cpp",
    ".js": "javascript", ".jsx": "javascript", ".ts": "typescript",
    ".tsx": "typescript", ".go": "go", ".java": "java", ".kt": "kotlin",
    ".scala": "scala", ".rb": "ruby", ".php": "php", ".swift": "swift",
    ".m": "objc", ".cs": "csharp", ".fs": "fsharp",
    ".sh": "bash", ".bash": "bash", ".zsh": "bash",
    ".hcl": "hcl", ".tf": "hcl",
    ".lua": "lua", ".dart": "dart", ".r": "r", ".jl": "julia",
    ".vim": "vim", ".el": "elisp", ".clj": "clojure", ".ex": "elixir",
    ".exs": "elixir", ".erl": "erlang", ".hs": "haskell", ".ml": "ocaml",
    ".nim": "nim", ".zig": "zig", ".v": "verilog", ".sv": "systemverilog",
    ".d": "d", ".sql": "sql", ".cmake": "cmake",
    ".html": "html", ".css": "css", ".scss": "css", ".less": "css",
    ".vue": "javascript", ".svelte": "javascript",
}

# Probe's directory skips: discovery's builtin set plus build-output and
# cache dirs a probe must never count. Single-sourced from
# _BUILTIN_SKIP_DIRS so discovery rule changes propagate automatically.
# T1: fixture/testdata subtrees pruned here too (probe/discovery parity).
_CODE_IGNORE_DIRS = _BUILTIN_SKIP_DIRS | _FIXTURE_SKIP_DIRS | {
    ".git", ".venv", "target", ".next", ".nuxt",
    "third_party", ".tricorder", "vendor",
}


def probe_project(project_root: str, exclude_globs: Optional[List[str]] = None) -> dict:
    """Cheap os.walk tally: language counts + total files + rough line estimate.

    No tree-sitter, no parsing, no ranking — just extension tally. Costs
    milliseconds, zero tokens. This is the turn-0 navigation probe, never a
    full map/token scan.

    Returns {"lang_counts": {lang: n}, "total_files": int, "est_lines": int,
             "top_lang": str}.
    """
    root_path = Path(project_root)
    if not root_path.is_dir():
        return {"lang_counts": {}, "total_files": 0, "est_lines": 0, "top_lang": ""}

    globs = exclude_globs or []
    lang_counts: dict = {}
    total_bytes = 0

    for dirpath, dirnames, filenames in os.walk(root_path):
        dirnames[:] = [d for d in dirnames if d not in _CODE_IGNORE_DIRS]
        for fname in filenames:
            try:
                rel = os.path.relpath(os.path.join(dirpath, fname), root_path)
            except ValueError:
                continue
            if any(fnmatch.fnmatch(rel, g) for g in globs):
                continue
            # Same file rules as discovery (discover_src_files): dotfiles
            # and skip extensions (minified, archives incl. .db, media,
            # data) are never code files. Shared constants, so discovery
            # rule changes propagate automatically. Residual drift vs
            # discovery: gitignore trees, oversize files, TC-002 envelopes
            # (the probe is uncapped by design) — errs toward detect-first,
            # the conservative side on burn.
            if fname.startswith("."):
                continue
            low = fname.lower()
            if any(low.endswith(ext) for ext in _SKIP_EXTS | _BINARY_MEDIA_EXTS | _ARCHIVE_EXTS | _DATA_EXTS | _MINIFIED_SUFFIXES):
                continue
            # T1: same fixture/hash-asset rule as discovery (shared
            # helper, so rule changes propagate automatically).
            if _is_fixture_or_hash_asset(rel.replace(os.sep, "/"), low):
                continue
            # T1 mechanism 2: same minified-blob sniff as discovery
            # (.js/.css only, bounded head read — probe stays cheap).
            if _is_minified_blob(os.path.join(dirpath, fname), low):
                continue
            ext = os.path.splitext(fname)[1].lower()
            lang = CODE_EXTENSIONS.get(ext)
            if not lang:
                continue
            lang_counts[lang] = lang_counts.get(lang, 0) + 1
            try:
                total_bytes += os.path.getsize(os.path.join(dirpath, fname))
            except OSError:
                pass

    total_files = sum(lang_counts.values())
    # ponytail: ~40 bytes/line average across languages. A probe, not a census.
    est_lines = total_bytes // 40 if total_bytes else 0
    top_lang = max(lang_counts, key=lang_counts.get) if lang_counts else ""
    return {"lang_counts": lang_counts, "total_files": total_files,
            "est_lines": est_lines, "top_lang": top_lang}


def format_probe_digest(probe: dict, project_root: str) -> str:
    """Turn the probe tally into the unified turn-0 digest text.

    Single source of truth: CLI --probe-digest, the Hermes plugin, and the DSH
    plugin all emit this exact string so turn-0 content is identical everywhere.
    Scale only — file/language/line counts, no tool pointers, no turn language.
    Navigation belongs to the caller (directive ladder, plugin scaffolding):
    a shared digest must not name tools that exist in only one harness.
    """
    total = probe.get("total_files", 0)
    if not total:
        return ""
    lang_counts = probe.get("lang_counts", {})
    est_lines = probe.get("est_lines", 0)
    top3 = sorted(lang_counts.items(), key=lambda x: -x[1])[:3]
    lang_str = ", ".join(f"{n} {lang}" for lang, n in top3)
    lines_str = f"~{est_lines // 1000}K lines" if est_lines >= 1000 else f"~{est_lines} lines"
    return f"{total} code files ({lang_str}), {lines_str}."


# =============================================================================
# Graph Query DSL Parser (M0.10)
# =============================================================================

@dataclass
class QueryModifiers:
    """Modifiers for a single traversal step."""
    depth: int = 1
    exclude_globs: List[str] = None
    include_globs: List[str] = None
    symbol_type: Optional[str] = None  # function, class, method, variable
    limit: int = 100

    def __post_init__(self):
        if self.exclude_globs is None:
            self.exclude_globs = []
        if self.include_globs is None:
            self.include_globs = []


@dataclass
class TraversalStep:
    """A single traversal step in the query."""
    kind: str  # "callers", "callees", "refs", "defs", "tests_for"
    target: str  # symbol name to start from
    modifiers: QueryModifiers


@dataclass
class ParsedQuery:
    """Complete parsed query with multiple chained steps."""
    steps: List[TraversalStep]


TEST_FILE_GLOBS = (
    "*/tests/*",
    "*/test/*",
    "*/__tests__/*",
    "test_*",
    "*_test.*",
    "*.test.*",
    "*_spec.*",
)
"""Path patterns (POSIX, matched against full path and basename) that identify
test files across common layouts: pytest/unittest (test_*.py, *_test.py,
tests/), Go (*_test.go), JS/TS (*.test.js, __tests__/), RSpec (*_spec.rb)."""


def is_test_file(path: str) -> bool:
    """Return True if path looks like a test file.

    Used by the tests_for graph traversal to restrict callers to test files.
    Matches against both the full POSIX path and the basename so bare
    filenames (no directory) work too.
    """
    name = path.replace("\\", "/")
    base = name.rsplit("/", 1)[-1]
    # The "/" + name probe lets "*/tests/*"-style globs match bare paths
    # like "tests/test_a.py" (fnmatch '*' can match empty, but the literal
    # '/' in the pattern still needs a character to anchor against).
    candidates = (name, "/" + name, base)
    return any(
        fnmatch.fnmatchcase(cand, pat)
        for cand in candidates
        for pat in TEST_FILE_GLOBS
    )


_SYMBOL_SEGMENT_SPLIT = re.compile(r'::|\.|_|-|/|\s|#')


def symbol_boundary_rank(name: str, query_lower: str) -> int:
    """Word-boundary rank of a symbol name against a symbols query (T3,
    SPEC-symbols-definition-priority).

    0 = full-name equality (the definition site itself); 1 = the query
    equals a separator-delimited segment (`HasMany` in
    `Builder::HasMany`); 2 = pure superstring match
    (`...HasMany...Test`). Deterministic, stdlib-only, language-agnostic.
    Shared by search_symbols ranking; the test-path demotion key lives
    at the call site (is_test_file) so each rule stays single-sourced.
    """
    nl = name.lower()
    if nl == query_lower:
        return 0
    for seg in _SYMBOL_SEGMENT_SPLIT.split(name):
        if seg and seg.lower() == query_lower:
            return 1
    return 2


_WORD_SPLIT = re.compile(r"[_\-\s\./]+")


def _camel_split(word: str):
    """Split a camelCase/CamelCase/screaming token into words. Deterministic."""
    return [w for w in re.split(
        r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])", word) if w]


# Small verb synonym groups for deterministic query expansion (no ML).
# Each group lists interchangeable verbs commonly swapped in identifiers
# (get/fetch, set/store...). Expansion is single-word substitution only.
_SYNONYM_GROUPS = (
    ("get", "fetch", "load", "retrieve", "read"),
    ("set", "store", "write", "save", "put"),
    ("create", "make", "build", "new"),
    ("delete", "remove", "drop", "clear"),
    ("find", "search", "lookup", "locate"),
    ("pack", "dump", "serialize"),
    ("unpack", "parse", "deserialize"),
)
_SYN_MAP = {}
for _g in _SYNONYM_GROUPS:
    for _w in _g:
        _SYN_MAP.setdefault(_w, set()).update(x for x in _g if x != _w)


def query_variants(query: str):
    """Deterministic orthographic variants for a retrieve-0 rescue (no LLM).

    Strips C++-style decorations off a query (template args, parens, namespace
    qualifier) and re-joins the word parts under every separator/case form so a
    dead-end exact lookup like `PCM::AddToBuffer<128,128>` or `Add_To_buffer`
    still resolves to the base symbol name. Results of a rescue are flagged
    'fuzzy' downstream so the agent/judge know they are not exact-name hits.
    ponytail: case fold + separator + camel split only; no stemmer, add one if
    plural/tense variants measurably miss.
    """
    q = query.strip()
    core = re.sub(r"<[^<>]*>", "", q)      # strip template args <128,128>
    core = re.sub(r"[()]", "", core)       # strip parens (incl. std::map<int>)
    core = core.split("::")[-1]            # namespace -> basename
    # Dot-qualified idiom (Python/JS: Model.save) -> stored :: form.
    # Qualified tags are stored as Class::method, so a natural "Model.save"
    # query could never hit the real tag and fell through to fuzzy junk.
    # Seed the :: form (and lowercase) as top-ranked variants.
    q_cc = q.replace(".", "::") if "." in q else None
    words = [w for part in _WORD_SPLIT.split(core) for w in _camel_split(part) if w]
    if not words:
        words = [core]
    variants = {q, q.lower()}
    if q_cc:
        variants.add(q_cc)
        variants.add(q_cc.lower())
    for sep in ("_", "-", "", " "):
        variants.add(sep.join(words))
        variants.add(sep.join(words).lower())
    variants.add("".join(w.lower() for w in words))
    # Synonym-swapped forms: single-word substitution from _SYN_MAP, joined
    # forms only (bounded: one substitution per variant, cap extras).
    wl = [w.lower() for w in words]
    extra = 0
    for i, w in enumerate(wl):
        for syn in sorted(_SYN_MAP.get(w, ())):
            if extra >= 20:
                break
            swapped = list(wl)
            swapped[i] = syn
            variants.add("_".join(swapped))
            variants.add("".join(swapped))
            extra += 1
    variants.discard("")
    # Prefer the base-name/joined forms, NEVER bare word fragments (a bare
    # 'get' over-matches every get_* symbol and caps the rescue before the
    # specific base arrives). Keep the raw-decorated forms last — they should
    # only win when nothing else did. ponytail: no stemming.
    def _rank(v):
        base_l = "".join(w.lower() for w in words)
        if q_cc and v.lower() == q_cc.lower():
            return -1  # dotted query's :: reading outranks the joined base
        if v.lower() == base_l:
            return 0
        if v.lower() == "".join(words).lower():
            return 1
        if v == q:
            return 3
        return 2
    return sorted(variants, key=lambda s: (_rank(s), len(s), s))


def tokenize_identifier(name: str):
    """Split an identifier into lowercase word tokens (separators + camel)."""
    return [w.lower() for part in _WORD_SPLIT.split(name)
            for w in _camel_split(part) if w]


# Language keywords as query noise in the retrieve-0 rescue pass
# (search_identifiers / search_symbols edit-distance + token-overlap).
# 2026-09-25 loop autopsy: "func MainSSA" rescued to FuncID_runtime_main
# ({"func","main"} is a genuine 2/3 majority) and "func Main" to funcMap
# (d<=2 on the keyword-loaded core "funcmain"). "func" is syntax, not
# signal. Applied to the QUERY side of rescue scoring only — tier-1
# exact/substring matching is untouched (rescue fires only on empty),
# so literal "func..." names still hit directly. Minimal on purpose:
# declaration keywords; extend only with loop-evidenced additions.
CODE_QUERY_STOPWORDS = frozenset(
    "func fn def class var const type struct interface".split()
)


def rescue_query_tokens(query: str):
    """(qcore, qtok) for the rescue pass with code keywords stripped.

    Falls back to the raw lowercased query / full token set when
    stripping empties the query (e.g. query is only keywords), so
    behavior degrades to today's instead of cliffing to nothing.
    """
    toks = [t for t in tokenize_identifier(query)
            if t not in CODE_QUERY_STOPWORDS]
    if not toks:
        toks = tokenize_identifier(query)
    return "".join(toks) or query.lower(), set(toks)


# Filler words in natural-language detect queries ("which function", "the",
# "into"). Applied to the QUERY side only: short code tokens like "is"/"in"
# keep their meaning inside identifier spans and are never stripped there.
NL_QUERY_STOPWORDS = frozenset(
    "a an the and or as at by for from in into of on to with "
    "is are was were be been being do does did done have has had "
    "that this these those it its which what when where how why "
    "then than so such no nor own same too very can will just shall may "
    "i me my we our you your he him his she her they them their "
    "s t ve re ll d m".split()
)

# Synonym groups for the content-backed detect tier, canonicalized to the
# first element so "arguments" (query) meets "args" (identifier). Verb
# groups mirror _SYNONYM_GROUPS; noun groups bridge NL plurals/abstractions
# to the terse names code actually uses.
_CONTENT_SYNONYM_GROUPS = _SYNONYM_GROUPS + (
    ("args", "argument", "arguments"),
    ("params", "parameter", "parameters"),
    # Q1 pilot: the NL query says "dependency" while the code says
    # "dependant" (_solve_generator's parameter). Nominal/adjectival
    # forms of the same root must meet, or the token can never match.
    ("depend", "dependency", "dependencies", "dependant", "dependants",
     "dependent", "dependents"),
    # Q3 pilot: the NL query says "dictionary" while the code says
    # "dict". The ubiquitous code abbreviation must meet its NL
    # expansion.
    ("dict", "dictionary", "dictionaries"),
)
_CONTENT_CANON = {}
for _g in _CONTENT_SYNONYM_GROUPS:
    for _w in _g:
        _CONTENT_CANON.setdefault(_w, _g[0])

# Words whose trailing "s" is not a plural: the inflection strip in
# canonical_token must leave them alone ("news" is not "new").
_INFLECTION_EXCEPTIONS = frozenset({"news"})


def canonical_token(tok: str) -> str:
    """Map a token to its synonym-group canonical form, else itself.

    Inflection-aware: "builds" folds to "build" first so it meets the
    ("create","make","build","new") group. The strip only applies when the
    stripped form is actually a group member, so non-group words like
    "responses" or "status" pass through unchanged (their plural handling
    stays in the caller's plural-insensitive matcher). A tiny exception
    list covers words whose trailing "s" is not a plural ("news" is not
    "new").
    """
    hit = _CONTENT_CANON.get(tok)
    if hit is not None:
        return hit
    if (len(tok) > 3 and tok.endswith("s") and not tok.endswith("ss")
            and tok not in _INFLECTION_EXCEPTIONS):
        hit = _CONTENT_CANON.get(tok[:-1])
        if hit is not None:
            return hit
    return tok


def levenshtein(a: str, b: str, max_dist: int = 2) -> int:
    """Edit distance with early exit past max_dist (stdlib only)."""
    if a == b:
        return 0
    if abs(len(a) - len(b)) > max_dist:
        return max_dist + 1
    if len(a) > len(b):
        a, b = b, a
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        row_min = i
        for j, cb in enumerate(b, 1):
            d = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb))
            cur.append(d)
            if d < row_min:
                row_min = d
        if row_min > max_dist:
            return max_dist + 1
        prev = cur
    return prev[-1]


def parse_query_dsl(dsl: str) -> ParsedQuery:
    """Parse graph query DSL into structured form.

    Grammar:
        query := traversal (pipe traversal)*
        traversal := kind '(' target ')' modifiers?
        kind := "callers" | "callees" | "refs" | "defs" | "tests_for"
        target := quoted string (single or double quotes)
        modifiers := (modifier)*
        modifier := "depth=" INT | "exclude=" GLOB | "include=" GLOB
                  | "type=" ("function"|"class"|"method"|"variable") | "limit=" INT
        pipe := "|"

    tests_for('name') is callers('name') restricted to test files — it answers
    "which tests exercise this symbol?".

    Examples:
        "callers('authenticate') depth=2"
        "callees('main') depth=1 exclude=tests/**"
        "refs('Config') type=class limit=50"
        "tests_for('authenticate')"                    # tests calling authenticate
        "callers('foo') | callees('bar') depth=3"
    """
    if not dsl or not dsl.strip():
        raise ValueError("Empty query string")

    steps = []
    # Split by pipe for chained traversals
    traversal_strs = [s.strip() for s in dsl.split('|')]

    for trav_str in traversal_strs:
        if not trav_str:
            continue

        # Match kind and target: kind('target') or kind("target")
        match = re.match(r'^(callers|callees|refs|defs|tests_for)\s*\(\s*([\'"])(.*?)\2\s*\)(.*)$', trav_str)
        if not match:
            raise ValueError(f"Invalid traversal syntax: {trav_str}")

        kind, _, target, modifiers_str = match.groups()

        # Parse modifiers
        mods = QueryModifiers()

        # depth=N
        depth_match = re.search(r'depth\s*=\s*(\d+)', modifiers_str)
        if depth_match:
            mods.depth = int(depth_match.group(1))

        # exclude=glob (can be multiple, comma-separated or repeated)
        # Match exclude=value where value can contain commas if quoted, or single values
        exclude_str = re.search(r'exclude\s*=\s*([^\s|]+)', modifiers_str)
        if exclude_str:
            # Split by comma but respect quoted strings
            val = exclude_str.group(1)
            # Simple split by comma for now - handles tests/**,vendor/**
            mods.exclude_globs = [g.strip() for g in val.split(',') if g.strip()]

        # include=glob
        include_str = re.search(r'include\s*=\s*([^\s|]+)', modifiers_str)
        if include_str:
            val = include_str.group(1)
            mods.include_globs = [g.strip() for g in val.split(',') if g.strip()]

        # type=function|class|method|variable
        type_match = re.search(r'type\s*=\s*(function|class|method|variable)', modifiers_str)
        if type_match:
            mods.symbol_type = type_match.group(1)

        # limit=N
        limit_match = re.search(r'limit\s*=\s*(\d+)', modifiers_str)
        if limit_match:
            mods.limit = int(limit_match.group(1))

        steps.append(TraversalStep(kind=kind, target=target, modifiers=mods))

    return ParsedQuery(steps=steps)


def _base(name: str) -> str:
    """Strip namespace prefix and signature suffix from a symbol name.

    Used for fuzzy matching between qualified query strings (e.g.
    'PCM::GetFrameAudioData') and stored symbol keys (e.g.
    'PCM::GetFrameAudioData() const -> FrameAudioData').
    """
    if '::' in name:
        name = name.split('::', 1)[-1]
    if '(' in name:
        name = name.split('(', 1)[0]
    elif name.endswith('()'):
        name = name[:-2]
    return name


def _qual(name: str) -> str:
    """Strip signature suffix but keep namespace scope.

    Companion to _base(): 'PCM::GetFrameAudioData() const -> FrameAudioData'
    becomes 'PCM::GetFrameAudioData', whereas _base() gives
    'GetFrameAudioData'. Used for graph traversal keys so a qualified query
    keeps its identity instead of degrading to the bare name (F1).
    """
    if '(' in name:
        name = name.split('(', 1)[0]
    return name


def _scope(name: str) -> Optional[str]:
    """Namespace scope of a symbol name, or None if unqualified.

    'A::B::run' -> 'A::B'; 'run' -> None. Signature text is ignored.
    """
    q = _qual(name)
    if '::' in q:
        return q.rsplit('::', 1)[0]
    return None
