import asyncio
import json
import os
import logging
import sys
import threading
from collections import OrderedDict
from pathlib import Path
from typing import List, Optional, Dict, Any, Set
import dataclasses

# Pin this project's dir ahead of sys.path so `from utils import ...` / `from core import ...`
# resolve to THIS repo, not a same-named module in another venv/install (the Hermes agent
# shadowed D:/Projects/tricorder/utils.py with its own utils.py, killing the MCP server at import).
sys.path.insert(0, str(Path(__file__).resolve().parent))

from fastmcp import FastMCP, settings
from core import Tricorder
from database import drop_mapped_files
from utils import count_tokens, read_text, parse_gitignore, discover_src_files, SymbolRecord, repo_budget, parse_query_dsl, ParsedQuery, get_cache_root, safe_write, db_root_matches, _db_writable, resolve_or_none
from scm import get_scm_fname
from importance import filter_important_files
from ctags_probe import probe_and_narrow

# Pre-scan DB lives in canonical cache root (get_cache_root() -> .tricorder/db)
PRE_SCAN_DB_DIR = get_cache_root() / "db"

def _escalation_hint(tool: str, query: str, n_results: int, rescue_used: bool,
                     rescue_kind: str = "fuzzy"):
    """Deterministic next-rung signal for empty/fuzzy lookups (no model).

    Decision table over already-computed signals only:
    - 0 hits (even after rescue) -> point at the next ladder rung.
    - fuzzy rescue fired -> verify the candidate in source via detail.
    - content rescue fired -> same, with the accurate provenance.
    Returns None when the result needs no escalation.
    # ponytail: fixed table, no heuristics beyond empty/fuzzy; extend only
    # with new measurable signals (e.g. budget-truncated), never content.
    """
    if n_results == 0 and query:
        nxt = {"detect": "symbols", "symbols": "query"}.get(tool, "detail")
        return {"next_rung": nxt, "reason": "empty",
                "evidence": {"tool": tool, "query": query, "rescue_tried": True},
                "message": f"No {'symbol' if tool == 'symbols' else 'identifier'} hit for "
                           f"'{query}' (exact + fuzzy tried). Try {nxt} or widen the query."}
    if rescue_used and n_results:
        if rescue_kind == "content":
            return {"next_rung": "detail", "reason": "content_verify",
                    "evidence": {"tool": tool, "query": query},
                    "message": "Content-backed rescue fired — candidates matched "
                               "your description's tokens in docstrings, bodies, or "
                               "call sites, not the identifier. Verify via detail "
                               "before asserting/editing."}
        return {"next_rung": "detail", "reason": "fuzzy_verify",
                "evidence": {"tool": tool, "query": query},
                "message": "Orthographic rescue fired — candidates are lookalikes, "
                           "not exact hits. Verify via detail before asserting/editing."}
    return None


# Thin wrapper kept for backward compat (tests import this name).
def find_src_files(directory: str, exclude_globs: Optional[List[str]] = None) -> List[str]:
    # TC-002: surface the resource-envelope partial-scan report on the module
    # so callers (tricorder_scan auto-discovery) can warn the agent.
    return discover_src_files(directory, use_gitignore=True, exclude_globs=exclude_globs,
                              report=_last_scan_report)


# TC-002: populated by find_src_files() so the scan envelope warning can be
# attached to the response when the walk hit a resource budget.
_last_scan_report: dict = {}

# Sentinel for _attach_scan_warning: "no snapshot was taken" (legacy global
# fallback) vs an explicit None snapshot (clean scan / no discovery ran).
_UNSET = object()

# Configure logging - only show errors
root_logger = logging.getLogger()
root_logger.setLevel(logging.ERROR)

# Create console handler for errors only
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.ERROR)
console_formatter = logging.Formatter('%(levelname)-5s %(asctime)-15s %(name)s:%(funcName)s:%(lineno)d - %(message)s')
console_handler.setFormatter(console_formatter)
root_logger.addHandler(console_handler)

# Suppress FastMCP logs
fastmcp_logger = logging.getLogger('fastmcp')
fastmcp_logger.setLevel(logging.ERROR)
# Suppress server startup message
server_logger = logging.getLogger('fastmcp.server')
server_logger.setLevel(logging.ERROR)

log = logging.getLogger(__name__)

# Set global stateless_http setting
settings.stateless_http = True

# Create MCP server
mcp = FastMCP("tricorder")

# No cache: re-checked on every call. The lookup costs two exists() checks
# plus one read-only meta open — trivial next to a scan — and a cached
# "no DB" answer would hide a canonical DB created by `tricorder --init`
# after the server started (scans would silently run in-memory, diffs
# would report everything as added).
def _canonical_db_for(project_root: str) -> Optional[str]:
    """First existing DB: <root>/.tricorder/db/<name>.db (--init canonical),
    else <cache>/db/<name>.db (pre_scan default). None if neither mapped.

    The lookup is by directory basename, so a same-named repo elsewhere can
    leave a colliding DB in the shared cache; db_root_matches rejects those
    (serving another repo's index would silently corrupt answers)."""
    name = f"{Path(project_root).name}.db"
    for cand in (Path(project_root) / ".tricorder" / "db" / name,
                 PRE_SCAN_DB_DIR / name):
        try:
            if cand.exists() and db_root_matches(str(cand), project_root):
                return str(cand)
        except Exception:
            continue
    return None


# Manual cache (was @lru_cache): the resolved DB path is re-checked on every
# call, and the cached instance is rebuilt when it changes — e.g. a canonical
# DB created by `tricorder --init` after the server started must take effect,
# not stay invisible behind a stale in-memory instance.
#
# Thread-safety: tool handlers run via asyncio.to_thread, so concurrent calls
# can race a cold root (double 9s+ construction) or hit check-then-act
# KeyErrors on move_to_end/popitem. One lock guards the whole get-or-create;
# warm hits are dict ops, so the lock is uncontended in the common case.
_tricorder_cache: "OrderedDict[str, tuple]" = OrderedDict()
_tricorder_cache_lock = threading.Lock()
_TRICORDER_CACHE_MAX = 32


def _db_file_ident(db_path: Optional[str]) -> Optional[tuple]:
    """Identity of the DB file behind db_path: (st_dev, st_ino), or None.

    Detects the file being *replaced* under a cached instance — e.g.
    `tricorder --init --wipe` while the server is running. On POSIX the
    unlink succeeds and the server's old connection keeps writing to the
    unlinked inode while the path points at a new file; on the next call the
    changed identity forces a rebuild onto the new file instead of serving
    the stale handle. Ordinary scan writes keep the inode, so they never
    trigger a rebuild."""
    if not db_path:
        return None
    try:
        st = os.stat(db_path)
    except OSError:
        return None
    return (st.st_dev, st.st_ino)


def _close_cached_tricorder(instance: "Tricorder") -> None:
    """Best-effort close of a discarded cached instance's DB handle."""
    if instance is None:
        return
    try:
        # Prefer Tricorder.close() (checkpoint + release + disarm); fall
        # back to closing the store directly for foreign shapes.
        close = getattr(instance, "close", None)
        if callable(close):
            close()
            return
        store = getattr(instance, "_db_store", None)
        if store is not None:
            store.close()
    except Exception:
        pass


def _get_tricorder(project_root: str) -> "Tricorder":
    """Reuse one Tricorder per root across tool calls (TC-011).

    Construction re-scans find_src_files + re-parses every file (9s+ per
    symbols call in bench). Keeping the instance alive lets tree_cache and
    _cross_file_index_cache persist in-process so repeat looks at the same
    repo are warm. The instance holds its own per-field locks, so reuse
    across stateless HTTP calls is safe. exclude_unranked=True always drops
    untagged/bloat files (per user: bloat -> exclude always).
    ponytail: single key (root), bounded LRU.
    """
    # Check for pre-scan DB (in-repo canonical first, cache fallback).
    # Same unwritable-canonical guard as the CLI map path: an existing
    # but read-only DB can't back a scan (the extractor gate DELETEs on
    # first use), so degrade to in-memory instead of crashing.
    db_path = _canonical_db_for(project_root)
    if db_path and not _db_writable(db_path):
        log.warning(f"Canonical DB {db_path} is not writable; "
                    "this MCP scan runs in-memory (no resumption).")
        db_path = None
    ident = _db_file_ident(db_path)

    with _tricorder_cache_lock:
        cached = _tricorder_cache.get(project_root)
        if cached is not None and cached[0] == db_path and cached[1] == ident:
            _tricorder_cache.move_to_end(project_root)
            return cached[2]
        if cached is not None:
            # Path changed, or the file was replaced under us (--init
            # --wipe): drop the stale handle so nothing keeps writing to
            # an unlinked inode.
            _close_cached_tricorder(cached[2])

        instance = Tricorder(
            root=project_root,
            token_counter_func=lambda text: count_tokens(text, "gpt-4"),
            file_reader_func=read_text,
            output_handler_funcs={'info': log.info, 'warning': log.warning, 'error': log.error},
            verbose=False,
            exclude_unranked=True,
            use_db=True,
            db_path=db_path,
        )
        _tricorder_cache[project_root] = (db_path, ident, instance)
        _tricorder_cache.move_to_end(project_root)
        while len(_tricorder_cache) > _TRICORDER_CACHE_MAX:
            _evicted_root, _evicted = _tricorder_cache.popitem(last=False)
            # Don't leak the evicted instance's sqlite handle (long-running
            # server, many roots): close it now that nothing references it.
            _close_cached_tricorder(_evicted[2])
        return instance

# ponytail: advisory tier tracker — survives across calls within a server process.
# Can't enforce agent behavior (MCP is stateless per call) but can warn in the response.
# Bounded LRU (OrderedDict) prevents unbounded growth across many project roots.
# Guarded by _tier_history_lock: tool handlers run on threads (asyncio.to_thread)
# and the check-then-act sequences below (in/move_to_end, len/popitem) race
# without it — observed as KeyError crashes under concurrent calls.
_MAX_TIER_HISTORY = 128

_tier_history_store: "OrderedDict[str, dict]" = OrderedDict()
_tier_history_lock = threading.Lock()


def _tier_history_get(project_root: str) -> Optional[dict]:
    """Get tier history for a project root (LRU-bounded)."""
    with _tier_history_lock:
        if project_root in _tier_history_store:
            # Move to end (most recently used)
            _tier_history_store.move_to_end(project_root)
            return _tier_history_store[project_root]
        return None


def _tier_history_set(project_root: str, value: dict) -> None:
    """Set tier history for a project root (LRU-bounded with explicit eviction)."""
    with _tier_history_lock:
        if project_root in _tier_history_store:
            # Update existing - move to end
            _tier_history_store.move_to_end(project_root)
        elif len(_tier_history_store) >= _MAX_TIER_HISTORY:
            # Evict least recently used
            _tier_history_store.popitem(last=False)
        _tier_history_store[project_root] = value


def _validate_project_root(project_root: str) -> tuple[Optional[str], Optional[Path]]:
    """
    Validate and resolve project_root.

    Returns:
        (error_message, resolved_path)
        - If valid: (None, Path)
        - If invalid: (error_string, None)
    """
    try:
        # Resolve absolute path, resolving symlinks
        root_path = Path(project_root).resolve(strict=True)
    except (OSError, FileNotFoundError):
        return (f"Project root not found or inaccessible: {project_root}", None)

    if not root_path.is_dir():
        return (f"Project root is not a directory: {project_root}", None)

    # Ensure path is readable
    if not os.access(root_path, os.R_OK):
        return (f"Project root not readable (permission denied): {project_root}", None)

    return (None, root_path)

def _validate_file_containment(file_path: str, project_root: Path) -> Optional[str]:
    """TC-006: verify a resolved file path stays inside project_root.

    Returns None if contained, or an error string if the path escapes.
    """
    resolved = Path(file_path).resolve()
    try:
        resolved.relative_to(project_root)
    except ValueError:
        return f"File path escapes project root: {file_path}"
    return None

def _savings_pct(token_estimate: int, full_repo_estimate: int) -> float:
    """% of full-repo context saved by a token estimate. 0 when repo is empty or
    the estimate exceeds the repo (a tier-1 map can cost more than reading it)."""
    if not full_repo_estimate:
        return 0.0
    return round(max(0.0, 1 - token_estimate / full_repo_estimate) * 100, 1)


# Break-even constants, sized from the two navigation benchmarks
# (2026-09-20). Small repo: 76 files — tricorder 8 steps / 23.0 KB /
# 9.3 s vs baseline 12 steps / 9.1 KB / 0.06 s (index buys nothing per
# query). Django: 7,116 files, 6,046 indexed — index 50.6 s; per query
# 8 steps / 12.8 KB vs baseline 13 steps / 31.6 KB (saves ~5
# round-trips, ~60% bytes).
_INDEX_S_PER_FILE = 50.6 / 6046  # ~0.0084 s/file, through the Django point
_INDEX_FIXED_S = 5.0              # floor: process startup + cache overhead
_SMALL_REPO_FILES = 200           # below this, one-off queries skip the scan
_STEPS_SAVED_PER_QUERY = 5        # 13 -> 8 steps (Django bench)
_S_PER_ROUND_TRIP = 45            # agent-latency assumption; stated, not hidden


def _scan_break_even_advisory(n_files: int) -> Optional[str]:
    """Advise (never refuse) whether a full scan is worth the upfront cost.

    Rule: scan_cost < per-query savings x expected queries. Small repos
    show negative per-query returns (plain search wins), so one-off
    queries should skip the scan; large repos save ~5 round-trips and
    ~60% bytes per query, so multi-query agent sessions still benefit.
    Returns None when there is nothing to advise on.
    """
    if n_files <= 0:
        return None
    index_s = max(_INDEX_FIXED_S, _INDEX_S_PER_FILE * n_files)
    if n_files < _SMALL_REPO_FILES:
        return (
            f"Small repo ({n_files} files): a full scan costs ~{index_s:.0f}s "
            "but buys little per query — at this size plain search measured "
            "faster and leaner (76-file bench: 9 KB / 0.06s baseline vs "
            "23 KB / 9.3s), i.e. negative per-query returns, so the index "
            "never pays for itself here. Skip the scan; detect/detail "
            "cold-parse in seconds."
        )
    break_even = max(
        1, round(index_s / (_STEPS_SAVED_PER_QUERY * _S_PER_ROUND_TRIP)))
    noun = "query" if break_even == 1 else "queries"
    return (
        f"Indexing {n_files} files costs ~{index_s:.0f}s one-time "
        "(incremental after). Each query saves ~5 round-trips and ~60% "
        "response bytes vs manual search (7k-file bench) — at ~45s per "
        f"round-trip the index pays for itself after ~{break_even} {noun}. "
        "Worth it for multi-query sessions; skip for one-offs."
    )


def _full_repo_tokens(project_root: str) -> int:
    """Estimate full-repo token cost (sum of raw source-file reads)."""
    return repo_budget(project_root, 0)["full_repo_estimate"]


def _budget_fields(resp: dict, full_repo_tokens: int, coverage_pct: Optional[float] = None) -> dict:
    """Add token_estimate/full_repo_estimate/savings_pct to a search-tool response.

    token_estimate = tokens of the serialized (non-error) response body.
    savings_pct = context saved vs reading the full repo. 0 when repo is empty.
    """
    tok = count_tokens(json.dumps(resp), "gpt-4")
    result = {
        "token_estimate": tok,
        "full_repo_estimate": full_repo_tokens,
        "savings_pct": _savings_pct(tok, full_repo_tokens),
    }
    if coverage_pct is not None:
        result["coverage_pct"] = coverage_pct
    return result


_TRUST_METADATA = {
    "source": "scanned_repository",
    "trust": "untrusted_repository_content",
}

def _mark_untrusted(resp: dict) -> dict:
    """TC-005: stamp repository-content trust metadata on response dicts."""
    resp.update(_TRUST_METADATA)
    return resp


def _detail_decoration_reserve() -> int:
    """Token overhead of the budget/trust fields added to a detail response.

    Measured from the real decoration dicts so the final serialized response
    honors max_tokens, not just the symbol portion.
    """
    import json as _json
    skeleton = {"token_estimate": 0, "full_repo_estimate": 0,
                "savings_pct": 0.0, "truncated": True}
    skeleton.update(_TRUST_METADATA)
    return count_tokens(_json.dumps(skeleton), "gpt-4")


_TRUNCATION_MARKER = "\n... [truncated to fit max_tokens]"


def _truncate_text_to_tokens(text: str, budget: int) -> str:
    """Truncate text to at most budget tokens (tiktoken), marking the cut.

    The truncation marker counts against the budget, so the result never
    exceeds it.
    """
    marker = _TRUNCATION_MARKER
    if budget <= 0 or not text:
        return ""
    try:
        import tiktoken as _tt
    except ImportError:
        # Fall back to a ~4 chars/token estimate when tiktoken is missing.
        return text[:budget * 4].rstrip() + marker
    enc = _tt.get_encoding("cl100k_base")
    marker_toks = len(enc.encode(marker))
    toks = enc.encode(text)
    if len(toks) <= budget:
        return text
    cut = enc.decode(toks[:max(0, budget - marker_toks)])
    # Prefer a clean line boundary over a mid-line cut.
    if "\n" in cut:
        cut = cut.rsplit("\n", 1)[0]
    return cut.rstrip() + marker


def _shave_body(symbol: dict) -> bool:
    """Remove ~10% of a symbol dict's body (in place), keeping the marker.

    Returns False when there is no body left to shave — the metadata floor.
    Used both by the budget trimmer and by the final total-budget check.
    """
    cur = symbol.get("body") or ""
    if not cur:
        return False
    base = cur[:-len(_TRUNCATION_MARKER)] \
        if cur.endswith(_TRUNCATION_MARKER) else cur
    new_len = int(len(base) * 0.9)
    if new_len >= len(base):
        return False
    trimmed = base[:new_len].rstrip()
    symbol["body"] = trimmed + _TRUNCATION_MARKER if trimmed else ""
    return True


def _final_budget_check(resp: dict, symbol: Optional[dict], max_tokens: int,
                        project_root: str) -> None:
    """Verify a fully-decorated response honors max_tokens, in place.

    The decoration reserve used during trimming is an estimate (placeholder
    values, serialization merge effects), so shave the symbol body until the
    serialized total actually fits. Refreshes the token-estimate fields
    afterwards; the 2-token headroom absorbs digit-length wobble when the
    refreshed estimates are re-serialized. Stops at the metadata floor
    (best effort — identity/signature are never cut).
    """
    trimmed = False
    for _ in range(4):
        if count_tokens(json.dumps(resp), "gpt-4") <= max_tokens - 2:
            break
        if symbol is None or not _shave_body(symbol):
            break
        trimmed = True
    if trimmed:
        resp["truncated"] = True
        resp.update(_budget_fields(resp, _full_repo_tokens(project_root)))


# Share of the call-list budget reserved for callers vs callees. References
# to the symbol are more valuable than references it makes, so callers take
# the larger share; callees are trimmed to their share first, then callers
# take whatever room remains — a hot symbol keeps a useful head of each
# instead of one list starving the other.
_CALLER_SHARE = 2
_CALLEE_SHARE = 1


def _trim_call_lists_top_n(symbol: dict, max_tokens: int, _tokens) -> bool:
    """Shorten callers/callees to weighted top-N heads that fit max_tokens.

    Heads are the most valuable entries: get_symbol_detail orders in-file
    references first and cross-file ones last. Callees (lower priority) are
    trimmed to their weighted share first — the full room when there are no
    callers to reserve for; an empty list reserves nothing — then callers
    take the remaining room, so neither list starves the other. The
    highest-priority non-empty list keeps at least one head while the body
    still has tokens to give (the body is shaved as needed): one reference
    beats a few more body lines. Records "<list>_total" / "<list>_omitted"
    for each non-empty list that was shortened — nothing is dropped
    silently, and counts survive even when a list is cut to zero.
    Per-list binary search keeps the trim at O(log n) serializations
    instead of O(n) pop-measure cycles for hot symbols. The final
    (callers, callees) pair is a directly measured fitting state.
    Returns True when either list was shortened.
    """
    callers = list(symbol.get("callers") or [])
    callees = list(symbol.get("callees") or [])
    n_callers, n_callees = len(callers), len(callees)
    if (n_callers == 0 and n_callees == 0) or _tokens() <= max_tokens:
        return False

    wsum = _CALLER_SHARE + _CALLEE_SHARE
    keyed = []
    for key, n in (("callers", n_callers), ("callees", n_callees)):
        if n:
            # Reserve the count fields up front so every probe measures
            # their real serialized cost.
            symbol[f"{key}_total"] = n
            symbol[f"{key}_omitted"] = n
            keyed.append(key)
    try:
        # Even empty lists may not fit (metadata alone over budget).
        symbol["callers"] = []
        symbol["callees"] = []
        if _tokens() > max_tokens:
            return True
        base = _tokens()  # both lists empty, count keys reserved
        room = max_tokens - base  # > 0 here

        def _fit_head(key, items, fits):
            """Largest head of items for which fits() holds."""
            lo, hi = 0, len(items)
            while lo < hi:
                mid = (lo + hi + 1) // 2
                symbol[key] = items[:mid]
                if fits():
                    lo = mid
                else:
                    hi = mid - 1
            symbol[key] = items[:lo]
            return lo

        # Lower-priority callees take their weighted share first — the full
        # room when there are no callers to reserve for — ...
        if n_callers:
            callee_share = room * _CALLEE_SHARE // wsum
        else:
            callee_share = room
        kept_callees = _fit_head(
            "callees", callees, lambda: _tokens() - base <= callee_share)
        # ...then callers take whatever room remains (their share plus any
        # the callees did not use). This final state is measured directly,
        # so the pair is guaranteed to fit.
        kept_callers = _fit_head(
            "callers", callers, lambda: _tokens() <= max_tokens)
        # Minimal-head protection: zeroing the highest-priority non-empty
        # list while the body still has tokens to give trades a reference
        # for a few more body lines. Shave the body until one head fits,
        # or the body is exhausted (counts then record the full cut).
        if n_callers:
            while not symbol["callers"] and _shave_body(symbol):
                kept_callers = _fit_head(
                    "callers", callers, lambda: _tokens() <= max_tokens)
        elif n_callees:
            while not symbol["callees"] and _shave_body(symbol):
                kept_callees = _fit_head(
                    "callees", callees, lambda: _tokens() <= max_tokens)
        for key, n, kept in (("callers", n_callers, kept_callers),
                             ("callees", n_callees, kept_callees)):
            if n:
                symbol[f"{key}_omitted"] = n - kept
        return True
    finally:
        for key in keyed:
            if symbol.get(f"{key}_omitted", 0) <= 0:
                symbol.pop(f"{key}_total", None)
                symbol.pop(f"{key}_omitted", None)


def _enforce_detail_budget(symbol: dict, max_tokens: int) -> bool:
    """Trim a tricorder_detail symbol dict to fit max_tokens, in place.

    Trim order: body first (head kept, cut marked), then callers/callees
    shortened to weighted top-N heads (freeing room to re-expand the body).
    Shortened lists keep explicit "<list>_total" / "<list>_omitted" counts —
    nothing is dropped silently. Name/file/line/signature metadata is never
    cut.
    Returns True when anything was trimmed.
    """
    import json as _json

    def _tokens() -> int:
        return count_tokens(_json.dumps(symbol))

    def _tokens_without_body() -> int:
        probe = dict(symbol, body="")
        return count_tokens(_json.dumps(probe))

    if _tokens() <= max_tokens:
        return False

    body = symbol.get("body") or ""
    # 1. Body: keep as much as fits alongside everything else.
    if body:
        symbol["body"] = _truncate_text_to_tokens(body, max_tokens - _tokens_without_body())
        if _tokens() <= max_tokens:
            return True

    # 2-3. Callers/callees: shrink both to weighted top-N heads (callers
    # take priority) with explicit totals, then give the body another
    # chance at the freed space. Counts survive even when a list is cut to
    # zero, so the payload is never silently empty.
    _trim_call_lists_top_n(symbol, max_tokens, _tokens)
    if body:
        symbol["body"] = _truncate_text_to_tokens(body, max_tokens - _tokens_without_body())
    if _tokens() <= max_tokens:
        return True

    # 4. Final clamp: the body above was budgeted in raw-text tokens, but
    # _tokens() measures the JSON-serialized form, where escaping
    # (newlines, quotes) inflates the count. Shave the body until the
    # serialized total actually fits. Metadata is never touched; if even
    # the metadata alone exceeds the budget, this is best-effort.
    while _tokens() > max_tokens and _shave_body(symbol):
        pass
    return True


# TC-001: explicit boundary markers around raw repo-derived text so an agent
# can't mistake injected comments/filenames/instructions for its own prompt.
_TRUST_BEGIN = "BEGIN UNTRUSTED REPOSITORY CONTEXT"
_TRUST_END = "END UNTRUSTED REPOSITORY CONTEXT"


def wrap_untrusted_content(text: str) -> str:
    """Wrap raw repo-derived text in explicit trust-boundary markers (TC-001)."""
    if not text:
        return text
    return f"{_TRUST_BEGIN}\n{text}\n{_TRUST_END}"


def _attach_scan_warning(resp: dict, warning=_UNSET) -> dict:
    """TC-002: attach the resource-envelope partial-scan warning if any.

    Callers pass the warning snapshotted synchronously right after
    find_src_files: _last_scan_report is a process-global dict, and an
    interleaved scan for another root can overwrite it across the awaits
    between discovery and response time. A snapshot of None (clean scan)
    wins over the global — otherwise the pre-round-17 race returns through
    the fallback. Omitting `warning` entirely keeps the legacy global
    fallback (backward compat). Pass None explicitly when no discovery ran
    (e.g. the caller supplied other_files) so nothing attaches.
    """
    warn = _last_scan_report.get("warning") if warning is _UNSET else warning
    if warn:
        resp["scan_warning"] = warn
    return resp


def _clamp_max_files(max_files: int) -> int:
    """TC-007: clamp max_files server-side — prevents callers from requesting
    absurd scan sizes (e.g. 999999999) that could exhaust resources.
    Discovery early-stops at MAX_SCAN_FILES (utils.py) only when that env cap
    is set (0 = unlimited by default), but clamp the param itself so
    downstream code never sees an absurd value."""
    MAX_ALLOWED_FILES_ENV = os.environ.get("TRICORDER_MAX_ALLOWED_FILES")
    MAX_ALLOWED_FILES = 999999999 if (MAX_ALLOWED_FILES_ENV is not None and MAX_ALLOWED_FILES_ENV == "0") else (int(MAX_ALLOWED_FILES_ENV) if MAX_ALLOWED_FILES_ENV else 10000)
    return min(max_files, MAX_ALLOWED_FILES)


@mcp.tool()
async def tricorder_scan(
    project_root: str,
    chat_files: Optional[List[str]] = None,
    other_files: Optional[List[str]] = None,
    token_limit: Any = 8192,  # Accept any type to handle empty strings
    exclude_unranked: bool = False,
    force_refresh: bool = False,
    mentioned_files: Optional[List[str]] = None,
    mentioned_idents: Optional[List[str]] = None,
    verbose: bool = False,
    max_context_window: Optional[int] = None,
    tier: int = 0,
    context_lines: int = 3,
    output_format: str = "text",
    max_files: int = 0,
    output_file: Optional[str] = None,
    dry_run: bool = False,
    exclude_globs: Optional[List[str]] = None,
    pre_index: Optional[str] = None,
    pre_index_max_files: int = 100,
    pre_index_include_parents: int = 0,
    full: bool = False,
) -> Dict[str, Any]:
    """Generate a repository map for the specified files, providing a list of function prototypes and variables for files as well as relevant related
    files. Provide filenames relative to the project_root. In addition to the files provided, relevant related files will also be included with a
    very small ranking boost.

    :param project_root: Root directory of the project to search.  (must be an absolute path!)
    :param chat_files: A list of file paths that are currently in the chat context. These files will receive the highest ranking.
    :param other_files: A list of other relevant file paths in the repository to consider for the map. They receive a lower ranking boost than mentioned_files and chat_files.
    :param token_limit: The maximum number of tokens the generated repository map should occupy. Defaults to 8192.
    :param exclude_unranked: If True, files with a PageRank of 0.0 will be excluded from the map. Defaults to False.
    :param force_refresh: If True, forces a refresh of the repository map cache. Defaults to False.
    :param mentioned_files: Optional list of file paths explicitly mentioned in the conversation and receive a mid-level ranking boost.
    :param mentioned_idents: Optional list of identifiers explicitly mentioned in the conversation, to boost their ranking.
    :param verbose: If True, enables verbose logging for the Tricorder generation process. Defaults to False.
    :param max_context_window: Optional maximum context window size for token calculation, used to adjust map token limit when no chat files are provided.
    :param max_files: Maximum number of files to auto-scan when other_files is not provided. Defaults to 0 (unlimited). Set to a positive number to cap the scan.
    :param output_file: If provided, write the map to this file path instead of returning it in the response. The response will contain only the file path and a token estimate — use this to avoid flooding the agent's context with large maps. Recommended for repos > 50 files.
    :param output_format: Output format — "text" (default) for prioritized definitions, "mermaid" for dependency graph as Mermaid flowchart.
    :param tier: 0 for definitions only (T0, cheapest), 1 for definitions + context lines (T1, expensive). Stop at the lowest tier that answers the question.
    :param context_lines: Lines of context around each definition when tier=1.
    :param dry_run: If True, estimate token budget without generating the map. Returns tag count, tokens per tag, tags at budget, full repo estimate, and a scan_advisory break-even note (advise, never refuse).
    :param exclude_globs: Optional list of glob patterns (POSIX, relative to project_root) to exclude from auto-scan, e.g. ["vendor/**", "third_party/**"]. Filters vendored/third-party subtrees before ranking so first-party code dominates the map. Ignored when other_files is explicitly provided.
    :param full: If True, emit the full repository map regardless of token_limit, disabling truncation. Use for full-repo indexing to disk. Defaults to False.
    :returns: A dictionary containing:
        - If dry_run: 'tags', 'tokens_per_tag', 'tags_at_budget', 'full_repo_estimate', and 'scan_advisory' (break-even advice on whether indexing is worth it).
        - If output_file is set: 'map_file' (path), 'token_estimate' (int), 'tier' (int), 'format' (str), 'report' (dict), and optionally 'tier_hint' (advisory).
        - If output_file is None: 'map' (the full map string), 'report' (dict) — backward compatible.
        - On success, all responses include 'source' ('scanned_repository') and 'trust' ('untrusted_repository_content') for provenance tracking.
        Or an 'error' key if an error occurred.
    """
    err, root_path = _validate_project_root(project_root)
    if err:
        return {"error": err}

    # 1. Handle and validate parameters
    # Convert token_limit to integer with fallback
    try:
        token_limit = int(token_limit) if token_limit else 8192
    except (TypeError, ValueError):
        token_limit = 8192
    
    # Ensure token_limit is positive
    if token_limit <= 0:
        token_limit = 8192
    
    # TC-007: clamp max_files server-side.
    max_files = _clamp_max_files(max_files)
    
    chat_files_list = chat_files or []
    mentioned_fnames_set = set(mentioned_files) if mentioned_files else None
    mentioned_idents_set = set(mentioned_idents) if mentioned_idents else None

    # 2. If a specific list of other_files isn't provided, scan the whole root directory.
    # This should happen regardless of whether chat_files are present.
    effective_other_files = []
    # Snapshot of this call's discovery warning (TC-002): _last_scan_report
    # is process-global, so capture it synchronously right after
    # find_src_files — before any await — or an interleaved scan for
    # another root would overwrite it and we'd attach their warning.
    scan_warning = _UNSET  # replaced below: snapshot, or explicit None
    if other_files:
        effective_other_files = other_files
        # No discovery ran for this call: an explicit None means "no
        # warning", so the legacy global fallback (possibly another
        # root's warning) can never attach here.
        scan_warning = None
    else:
        # Pre-index probe: if pre_index is given and no other_files provided, run ctags probe
        if pre_index:
            log.info(f"Probing ctags for symbol '{pre_index}' in {project_root}...")
            probed_rel_files = probe_and_narrow(
                project_root,
                pre_index,
                max_files=pre_index_max_files,
                include_parents=pre_index_include_parents
            )
            if probed_rel_files:
                log.info(f"Ctags probe matched {len(probed_rel_files)} files.")
                effective_other_files = probed_rel_files
                # Probe path runs no directory discovery: explicit None so
                # the global fallback can't attach another scan's warning.
                scan_warning = None
            else:
                log.warning(f"Ctags probe found no matches for '{pre_index}', falling back to auto-scan.")
        
        if not effective_other_files:
            log.info("No other_files provided, scanning root directory for context...")
            effective_other_files = find_src_files(project_root, exclude_globs=exclude_globs)
            # Snapshot before any await: see the scan_warning declaration above.
            scan_warning = _last_scan_report.get("warning")
            # Prefix cap (house rule): max_files caps the discovery prefix
            # FIRST, then already-mapped files within the prefix are dropped
            # so a resumed rising-cap run doesn't re-parse them. Fixed-cap
            # reruns add zero; resume with a rising cap.
            if max_files > 0 and len(effective_other_files) > max_files:
                log.warning(f"Auto-scanned {len(effective_other_files)} files, capping to {max_files}")
                effective_other_files = effective_other_files[:max_files]
            # Skip the drop when the canonical DB isn't writable — it can't
            # back this scan (degraded to in-memory above), so nothing in it
            # is authoritative for the window.
            _cand = _canonical_db_for(project_root)
            if _cand and not _db_writable(_cand):
                _cand = None
            _dropped = drop_mapped_files(
                effective_other_files, project_root, _cand)
            # When the drop empties a non-empty discovery (everything
            # already mapped), keep the capped list: the DB-backed dirty
            # diff skips clean files without re-parsing, so the scan still
            # renders from the index instead of "No files found".
            effective_other_files = _dropped or effective_other_files

    # Add a print statement for debugging so you can see what the tool is working with.
    log.debug(f"Chat files: {chat_files_list}")
    log.debug(f"Effective other_files count: {len(effective_other_files)}")

    # If after all that we have no files, we can exit early.
    if not chat_files_list and not effective_other_files:
        log.info("No files to process.")
        return {"map": "No files found to generate a map."}

    # 3. Resolve paths relative to project root. Unresolvable files
    # (symlink loops, dangling links) are skipped with a warning instead
    # of crashing the tool.
    def _resolve_or_skip(files):
        out = []
        for f in files:
            r = resolve_or_none(str(root_path / f))
            if r is None:
                log.warning(f"Skipping {f}: cannot resolve path")
            else:
                out.append(r)
        return out
    abs_chat_files = _resolve_or_skip(chat_files_list)
    abs_other_files = _resolve_or_skip(effective_other_files)
    
    # TC-006: reject any file paths that resolve outside the project root
    for f in abs_chat_files + abs_other_files:
        err = _validate_file_containment(f, root_path)
        if err:
            return {"error": err}
    
    # Remove any chat files from the other_files list to avoid duplication
    abs_chat_files_set = set(abs_chat_files)
    abs_other_files = [f for f in abs_other_files if f not in abs_chat_files_set]

    # 4. Instantiate and run Tricorder
    # Unified DB resolution: the scan path uses the same canonical lookup
    # as the other tools (in-repo <root>/.tricorder/db/<name>.db first,
    # shared-cache fallback) so a repo indexed by --init is never silently
    # scanned without its index. Previously _prescan_db_for saw only the
    # shared cache and missed in-repo DBs.
    db_path2 = _canonical_db_for(project_root)
    # Same unwritable-canonical guard as _get_tricorder: the scan path
    # below constructs its own Tricorder (not via _get_tricorder), so
    # without this an existing-but-read-only DB crashes the scan at
    # DBStore init (DDL+commit) while the drop window above already
    # treated the DB as absent. Degrade to in-memory like the CLI.
    if db_path2 and not _db_writable(db_path2):
        log.warning(f"Canonical DB {db_path2} is not writable; "
                    "this MCP scan runs in-memory (no resumption).")
        db_path2 = None

    try:
        repo_mapper = Tricorder(
            map_tokens=token_limit,
            root=str(root_path),
            token_counter_func=lambda text: count_tokens(text, "gpt-4"),
            file_reader_func=read_text,
            output_handler_funcs={'info': log.info, 'warning': log.warning, 'error': log.error},
            verbose=verbose,
            exclude_unranked=exclude_unranked,
            max_context_window=max_context_window,
            context_lines=context_lines if tier > 0 else 0,
            exclude_globs=exclude_globs,
            full_map=full,
            use_db=True,
            db_path=db_path2,
        )
    except Exception as e:
        log.exception(f"Failed to initialize Tricorder for project '{project_root}': {e}")
        return {"error": f"Failed to initialize Tricorder: {str(e)}"}

    # 5. Dry run / output_file — estimate + map to disk
    # ponytail: when output_file is set, the map goes to disk anyway — no need to
    # render it into context. Just return the estimate + metadata.
    # Agent can pass dry_run=True explicitly, or rely on output_file triggering it.
    try:
        if dry_run or output_file:
            ranked_tags, file_report = await asyncio.to_thread(
                repo_mapper.get_ranked_tags,
                chat_fnames=abs_chat_files,
                other_fnames=abs_other_files
            )
            if not ranked_tags:
                return {"error": "No tags extracted — tree-sitter may lack parsers for this language."}
            chat_rel = set(repo_mapper.get_rel_fname(f) for f in abs_chat_files)
            sample = ranked_tags[:10]
            sample_tree = repo_mapper.to_tree(sample, chat_rel, [])
            sample_tokens = repo_mapper.token_count(sample_tree)
            tokens_per_tag = sample_tokens / len(sample)
            tags_at_budget = int(token_limit / tokens_per_tag) if tokens_per_tag > 0 else 0

            if dry_run:
                full_repo_estimate = _full_repo_tokens(project_root)
                # Map is clamped to min(token_limit, full_repo) — honest best-case savings
                map_tokens_planned = min(token_limit, full_repo_estimate)
                result = {
                    "tags": len(ranked_tags),
                    "tokens_per_tag": round(tokens_per_tag, 0),
                    "tags_at_budget": tags_at_budget,
                    "full_repo_estimate": full_repo_estimate,
                    "token_estimate": map_tokens_planned,
                    "savings_pct": _savings_pct(map_tokens_planned, full_repo_estimate),
                    "definition_matches": file_report.definition_matches,
                    "reference_matches": file_report.reference_matches,
                    "total_files_considered": file_report.total_files_considered,
                }
                # Advisory tier hint: T0 incomplete (truncated at budget)
                if tags_at_budget < len(ranked_tags):
                    pct = round(tags_at_budget / len(ranked_tags) * 100, 1)
                    result["tier_hint"] = f"T0 incomplete: {tags_at_budget}/{len(ranked_tags)} tags fit ({pct}%). Consider tier=1 or higher token_limit."
                # Break-even gate: advise (never refuse) whether indexing is
                # worth it — sized from benchmark data, see
                # _scan_break_even_advisory.
                advisory = _scan_break_even_advisory(
                    file_report.total_files_considered)
                if advisory:
                    result["scan_advisory"] = advisory
                return _attach_scan_warning(_mark_untrusted(result), warning=scan_warning)

            # output_file path — generate the actual map, write to disk, return metadata
            if output_format == "mermaid":
                map_content = await asyncio.to_thread(
                    repo_mapper.to_mermaid,
                    chat_fnames=abs_chat_files,
                    other_fnames=abs_other_files,
                    mentioned_fnames=mentioned_fnames_set,
                    mentioned_idents=mentioned_idents_set
                )
                report_dict = {"excluded": {}, "definition_matches": 0, "reference_matches": 0, "total_files_considered": 0}
            else:
                map_content, file_report = await asyncio.to_thread(
                    repo_mapper.get_repo_map,
                    chat_files=abs_chat_files,
                    other_files=abs_other_files,
                    mentioned_fnames=mentioned_fnames_set,
                    mentioned_idents=mentioned_idents_set,
                    force_refresh=force_refresh
                )
                map_tokens_actual = count_tokens(map_content or "", "gpt-4")
                remaining_tokens = max(0, token_limit - map_tokens_actual)
                remaining_chars = remaining_tokens * 4
                excluded_list = list(file_report.excluded.items())
                capped_excluded = {}
                for path, reason in excluded_list:
                    entry_size = len(path) + len(reason) + 20
                    if len(capped_excluded) * 20 + entry_size > remaining_chars:
                        break
                    capped_excluded[path] = reason
                report_dict = {
                    "excluded": capped_excluded,
                    "excluded_total": len(file_report.excluded),
                    "definition_matches": file_report.definition_matches,
                    "reference_matches": file_report.reference_matches,
                    "total_files_considered": file_report.total_files_considered,
                    "coverage_pct": file_report.coverage_pct,
                }

            token_estimate = count_tokens(map_content or "", "gpt-4")
            full_repo_estimate = _full_repo_tokens(project_root)

            # TC-008: contain output_file writes to tricorder-managed storage only.
            # safe_write enforces the cache-root boundary; server output lives
            # under get_cache_root()/.tricorder/output (honors TRICORDER_CACHE_HOME).
            out_path = get_cache_root() / "output" / Path(output_file).name
            safe_write(out_path, map_content)
            result: Dict[str, Any] = {
                "map_file": str(out_path),
                "token_estimate": token_estimate,
                "full_repo_estimate": full_repo_estimate,
                "savings_pct": _savings_pct(token_estimate, full_repo_estimate),
                "tags": len(ranked_tags),
                "tokens_per_tag": round(tokens_per_tag, 0),
                "tags_at_budget": tags_at_budget,
                "estimated_index_tokens": int(tokens_per_tag * len(ranked_tags)),
                "tier": tier,
                "format": output_format,
                "report": report_dict,
                "coverage_pct": file_report.coverage_pct,
            }
            # Advisory tier hint: T0 incomplete (truncated at budget)
            if tags_at_budget < len(ranked_tags):
                pct = round(tags_at_budget / len(ranked_tags) * 100, 1)
                result["tier_hint"] = f"T0 incomplete: {tags_at_budget}/{len(ranked_tags)} tags fit ({pct}%). Consider tier=1 or higher token_limit."
            # Advisory tier hint: upgrade from previous tier
            prev = _tier_history_get(project_root)
            if prev:
                if tier > prev["last_tier"] and prev.get("map_file"):
                    result["tier_hint"] = (
                        f"Upgrading from T{prev['last_tier']} to T{tier}. "
                        f"The T{prev['last_tier']} map at {prev['map_file']} may have been sufficient — "
                        f"only escalate tiers if the previous tier genuinely failed to answer your question."
                    )
            _tier_history_set(project_root, {"last_tier": tier, "last_format": output_format, "map_file": str(out_path)})
            return _attach_scan_warning(_mark_untrusted(result), warning=scan_warning)

        # Stdout path (backward compat — no output_file, no dry_run)
        if output_format == "mermaid":
            map_content = await asyncio.to_thread(
                repo_mapper.to_mermaid,
                chat_fnames=abs_chat_files,
                other_fnames=abs_other_files,
                mentioned_fnames=mentioned_fnames_set,
                mentioned_idents=mentioned_idents_set
            )
            report_dict = {"excluded": {}, "definition_matches": 0, "reference_matches": 0, "total_files_considered": 0}
        else:
            map_content, file_report = await asyncio.to_thread(
                repo_mapper.get_repo_map,
                chat_files=abs_chat_files,
                other_files=abs_other_files,
                mentioned_fnames=mentioned_fnames_set,
                mentioned_idents=mentioned_idents_set,
                force_refresh=force_refresh
            )
            map_tokens_actual = count_tokens(map_content or "", "gpt-4")
            remaining_tokens = max(0, token_limit - map_tokens_actual)
            remaining_chars = remaining_tokens * 4
            excluded_list = list(file_report.excluded.items())
            capped_excluded = {}
            for path, reason in excluded_list:
                entry_size = len(path) + len(reason) + 20
                if len(capped_excluded) * 20 + entry_size > remaining_chars:
                    break
                capped_excluded[path] = reason
            report_dict = {
                "excluded": capped_excluded,
                "excluded_total": len(file_report.excluded),
                "definition_matches": file_report.definition_matches,
                "reference_matches": file_report.reference_matches,
                "total_files_considered": file_report.total_files_considered,
                "coverage_pct": file_report.coverage_pct,
            }
        _tok = count_tokens(map_content or "", "gpt-4")
        _full = _full_repo_tokens(project_root)
        return _attach_scan_warning(_mark_untrusted({"map": wrap_untrusted_content(map_content), "report": report_dict,
                "token_estimate": _tok,
                "full_repo_estimate": _full,
                "savings_pct": _savings_pct(_tok, _full),
                "coverage_pct": file_report.coverage_pct}), warning=scan_warning)

    except Exception as e:
        log.exception(f"Error generating repository map for project '{project_root}': {e}")
        return {"error": f"Error generating repository map: {str(e)}"}
    finally:
        # Per-call instance (not via _get_tricorder): release its sqlite
        # handle — otherwise every scan leaks a connection on the server.
        _close_cached_tricorder(repo_mapper)
    
@mcp.tool()
async def tricorder_detect(
    project_root: str,
    query: str,
    max_results: int = 10,
    context_lines: int = 1,
    include_definitions: bool = True,
    include_references: bool = True,
    pre_index: Optional[str] = None,
    pre_index_max_files: int = 100,
    pre_index_include_parents: int = 0,
    search_mode: str = "substring",  # "exact", "substring", "regex"
) -> Dict[str, Any]:
    """Search for identifiers in code files. Get back a list of matching identifiers with their file, line number, and context.

    Args:
        project_root: Root directory of the project to search.  (must be an absolute path!)
        query: Search query (identifier name)
        max_results: Maximum number of results to return
        context_lines: Lines of context around each hit (default 1; render
            diet — blank lines stripped, match line always kept).
        include_definitions: Whether to include definition occurrences
        include_references: Whether to include reference occurrences
        pre_index: Optional symbol to pre-index (narrow file set before search)
        pre_index_max_files: Max files from pre-index
        pre_index_include_parents: Include N parent dirs of matched files
        search_mode: Search mode - "exact" (whole word), "substring" (contains), "regex" (Python regex). Default: "substring".
    
    Returns:
        Dictionary containing search results or error message
    """
    err, root_path = _validate_project_root(project_root)
    if err:
        return {"error": err}

    project_root = str(root_path)

    # Validate search_mode
    if search_mode not in ("exact", "substring", "regex"):
        return {"error": f"Invalid search_mode: {search_mode}. Must be 'exact', 'substring', or 'regex'."}

    try:
        # Initialize Tricorder with search-specific settings
        repo_map = _get_tricorder(project_root)

        # Pre-index probe: narrow the file set to files containing the probe
        # symbol (same fast path tricorder_scan uses). Prevents full-tree walks
        # on huge repos (e.g. the Linux kernel) where a blind search across
        # every file is slow and cold-cache-flaky. Mirrors --pre-index on the CLI.
        files = None
        if pre_index:
            probed = probe_and_narrow(
                project_root, pre_index,
                max_files=pre_index_max_files,
                include_parents=pre_index_include_parents,
            )
            if probed:
                # probe_and_narrow returns paths relative to project_root; normalize
                # to absolute to match the tag loop's contract.
                files = [str(Path(project_root) / f) for f in probed]

        try:
            results, rescue_used = repo_map.search_identifiers(
                query,
                max_results=max_results,
                context_lines=context_lines,
                include_definitions=include_definitions,
                include_references=include_references,
                search_mode=search_mode,
                files=files,
            )
        except ValueError as e:
            return {"error": str(e)}

        resp = {"results": results}
        rescue_kind = ("content"
                       if any(r.get("quality") == "content" for r in results)
                       else "fuzzy")
        esc = _escalation_hint("detect", query, len(results), rescue_used,
                               rescue_kind)
        if esc:
            resp["escalation"] = esc
        resp.update(_budget_fields(resp, _full_repo_tokens(project_root)))
        return _mark_untrusted(resp)

    except Exception as e:
        log.exception(f"Error searching identifiers in project '{project_root}': {e}")
        return {"error": f"Error searching identifiers: {str(e)}"}

@mcp.tool()
async def tricorder_symbols(
    project_root: str,
    query: str = "",
    type: Optional[str] = None,
    file: Optional[str] = None,
    limit: int = 10,
) -> Dict[str, Any]:
    """Search for code symbols by name, type, or file path. Returns matching symbols with their name, type, file, line range, signature, docstring, language, and tree-sitter kind.

    Docstrings are capped at 200 chars in listings (truncated records carry
    docstring_omitted with the exact char count); the full docstring is
    available via tricorder_detail.

    Args:
        project_root: Root directory of the project to search. (must be an absolute path!)
        query: Substring match on symbol name (case-insensitive). Empty string matches all.
        type: Filter by symbol type — function, class, type, variable, method, or import. Exact match.
        file: Filter by file path — path contains the given string.
        limit: Maximum results to return. Defaults to 10, caps at 200.

    Returns:
        Dictionary containing 'symbols' (list of symbol records) or 'error' key.
    """
    err, root_path = _validate_project_root(project_root)
    if err:
        return {"error": err}

    project_root = str(root_path)

    try:
        repo_map = _get_tricorder(project_root)

        results, rescue = repo_map.search_symbols(
            query, type=type, file=file, limit=limit)

        resp = {"symbols": results, "total": len(results),
                "limit": min(max(limit, 1), 200)}
        esc = _escalation_hint("symbols", query, len(results), rescue)
        if esc:
            resp["escalation"] = esc
        resp.update(_budget_fields(resp, _full_repo_tokens(project_root)))
        return _mark_untrusted(resp)

    except Exception as e:
        log.exception(f"Error searching symbols in project '{project_root}': {e}")
        return {"error": f"Error searching symbols: {str(e)}"}

@mcp.tool()
async def tricorder_diff(
    project_root: str,
) -> Dict[str, Any]:
    """Show what changed in the working tree since the last scan (delta map).

    Compares current file fingerprints against the index's recorded
    file_state and returns added/modified/deleted files plus per-file tag
    heads for the added/modified files — a fraction of a full rescan.
    Render diet: tag lists are capped per file (default 50); exact totals
    stay in tag_counts, cuts are explicit in tags_omitted/tags_truncated.
    When the project was never scanned, every file reports as added with
    indexed=False and no tags are parsed (the file list IS the delta).
    Read-only: it never updates the index.

    Args:
        project_root: Root directory of the project (must be absolute path!)

    Returns:
        Dictionary with added/modified/deleted (relative paths),
        tags ({rel: [tag dicts]}, capped heads), tag_counts ({rel: exact
        int}), tags_omitted ({rel: int}), tags_truncated (bool), indexed
        (bool), plus budget fields.
    """
    err, root_path = _validate_project_root(project_root)
    if err:
        return {"error": err}

    project_root = str(root_path)

    # Diff is a reader: open the index frozen read-only (never via
    # _get_tricorder — that instance is shared with the write path and
    # a cached read-only connection would go stale while scans rewrite
    # the DB, violating read_only_connect's hold-briefly contract).
    # Dedicated instance per call: closed in the finally below so repeated
    # diffs don't leak sqlite handles on the long-running server.
    _db_path = _canonical_db_for(project_root)
    repo_map = None
    try:
        repo_map = Tricorder(
            root=project_root,
            token_counter_func=lambda text: count_tokens(text, "gpt-4"),
            file_reader_func=read_text,
            output_handler_funcs={'info': log.info, 'warning': log.warning, 'error': log.error},
            verbose=False,
            exclude_unranked=True,
            use_db=True,
            db_path=_db_path,
            db_read_only=bool(_db_path),
        )

        diff = repo_map.diff_against_index()
        resp = dict(diff)
        resp.update(_budget_fields(resp, _full_repo_tokens(project_root)))
        return _mark_untrusted(resp)

    except Exception as e:
        log.exception(f"Error computing diff for project '{project_root}': {e}")
        return {"error": f"Error computing diff: {str(e)}"}
    finally:
        _close_cached_tricorder(repo_map)

@mcp.tool()
async def tricorder_detail(
    project_root: str,
    file: str,
    name: str,
    line: int = 0,
    max_tokens: Optional[int] = None,
) -> Dict[str, Any]:
    """Get full details for a specific code symbol by file path, name, and optional line number.

    Returns the symbol record with additional fields:
      - body: the actual code body (first 500 chars)
      - callers: list of {file, line, cross_file} dicts — references to this symbol
      - callees: list of {name, file, line, cross_file} dicts — symbols this symbol calls
      - callers_total / callers_omitted, callees_total / callees_omitted:
        present only when the corresponding list was shortened to fit
        max_tokens, so a trimmed list never hides how much was dropped.
    Callers/callees are populated from tree-sitter reference captures:
      - In-file: references within the same file
      - Cross-file: full-repo scan matching references to definitions
    cross_file=True means the reference/definition is in a different file.

    If the symbol is not found, returns {"error": "not found"} with exit code 0.

    Args:
        project_root: Root directory of the project. (must be an absolute path!)
        file: File path containing the symbol (relative to project_root or absolute).
        name: Symbol name to look up.
        line: Optional line number to disambiguate symbols with the same name.
        max_tokens: Optional token budget for the response. When set, the body
            is truncated first (head kept, marked), then callees and callers
            are shortened to the largest top-N heads that fit, each keeping
            explicit "<list>_total" / "<list>_omitted" counts — signature
            metadata is never cut.
            Best-effort: name/file/line/signature and the response decorations
            always survive, so a budget below that floor can still be exceeded.
            The response gains "truncated": true when trimming occurred.

    Returns:
        Dictionary containing 'symbol' (symbol record dict) or 'error' key.
    """
    err, root_path = _validate_project_root(project_root)
    if err:
        return {"error": err}

    project_root = str(root_path)

    # Resolve file path — accept relative or absolute
    file_path = Path(file)
    if not file_path.is_absolute():
        file_path = Path(project_root) / file_path
    file_path = str(file_path.resolve())
    
    # TC-006: reject file paths that escape the project root
    err = _validate_file_containment(file_path, Path(project_root))
    if err:
        return {"error": err}

    if not os.path.isfile(file_path):
        return {"error": "not found"}

    try:
        repo_map = _get_tricorder(project_root)

        detail = repo_map.get_symbol_detail(file_path, name, line)
        if detail is None:
            return {"error": "not found"}

        resp = {"symbol": detail.to_dict()}
        trimmed = False
        if max_tokens is not None and max_tokens > 0:
            # Reserve room for the budget/trust decorations added below so
            # the final serialized response honors max_tokens.
            reserve = _detail_decoration_reserve()
            if _enforce_detail_budget(resp["symbol"], max(1, max_tokens - reserve)):
                trimmed = True
        if trimmed:
            resp["truncated"] = True
        resp.update(_budget_fields(resp, _full_repo_tokens(project_root)))
        resp = _mark_untrusted(resp)
        if max_tokens is not None and max_tokens > 0:
            # Final guarantee: the reserve above is an estimate, so verify
            # the serialized total and shave the body if drift pushed it
            # over (estimates refreshed inside).
            _final_budget_check(resp, resp["symbol"], max_tokens, project_root)
        return resp

    except Exception as e:
        log.exception(f"Error getting symbol details for '{name}' in '{file_path}': {e}")
        return {"error": f"Error getting symbol details: {str(e)}"}


@mcp.tool()
async def tricorder_locate(
    project_root: str,
    query: str,
    max_tokens: int = 2048,
    max_alternatives: int = 5,
) -> Dict[str, Any]:
    """Locate a symbol in one call: runs detect, then details the best match.

    Auto-escalation for the most common agent flow (find the symbol, show it),
    collapsing 3-4 round trips into one. Returns the best match's full detail
    (body/callers/callees, budgeted to max_tokens like tricorder_detail) plus
    a short list of alternative candidates for disambiguation.

    The best match prefers an exact-name definition; fuzzy rescue candidates
    are used only when nothing exact matched.

    Args:
        project_root: Root directory of the project (must be absolute path!)
        query: Symbol name to locate.
        max_tokens: Token budget for the matched detail (default 2048).
            Best-effort; metadata always survives (see tricorder_detail).
        max_alternatives: Max alternative candidates to list (default 5).

    Returns:
        Dictionary with query, match (symbol detail dict or None),
        alternatives ([{name, file, line, kind, quality}]), truncated (bool
        when the match was budgeted down), plus budget fields.
    """
    err, root_path = _validate_project_root(project_root)
    if err:
        return {"error": err}

    project_root = str(root_path)

    try:
        repo_map = _get_tricorder(project_root)

        candidates, _rescue = repo_map.search_identifiers(query, max_results=10)
        if not candidates:
            resp = {"query": query, "match": None, "alternatives": [],
                    "note": f"No matches for '{query}'."}
            resp.update(_budget_fields(resp, _full_repo_tokens(project_root)))
            return _mark_untrusted(resp)

        # Best match: exact-name definition first, then any exact hit,
        # then the top fuzzy candidate.
        qlower = query.lower()

        def _rank(c):
            return (c.get("quality") != "exact",
                    c.get("kind") != "def",
                    c.get("name", "").lower() != qlower,
                    c.get("file", ""), c.get("line", 0))

        best = min(candidates, key=_rank)
        rest = [c for c in candidates
                if (c["file"], c["line"], c["name"]) != (best["file"], best["line"], best["name"])]

        match = None
        truncated = False
        file_path = str(Path(project_root) / best["file"])
        detail = repo_map.get_symbol_detail(file_path, best["name"], best["line"])

        alternatives = [
            {"name": c["name"], "file": c["file"], "line": c["line"],
             "kind": c["kind"], "quality": c.get("quality", "exact")}
            for c in rest[:max(0, max_alternatives)]
        ]

        resp = {"query": query, "match": None, "alternatives": alternatives}
        if detail is None:
            resp["note"] = (f"Best candidate '{best['name']}' in {best['file']} "
                            f"could not be detailed; see alternatives.")

        if detail is not None:
            match = detail.to_dict()
            if max_tokens is not None and max_tokens > 0:
                # Wrapper overhead: every response field except the match
                # itself (query/alternatives/note). Measure it so the final
                # serialized response honors max_tokens, not just the symbol.
                wrapper_tokens = count_tokens(json.dumps(resp), "gpt-4")
                match_budget = max_tokens - wrapper_tokens - _detail_decoration_reserve()
                if _enforce_detail_budget(match, max(1, match_budget)):
                    truncated = True
            resp["match"] = match

        if truncated:
            resp["truncated"] = True
        resp.update(_budget_fields(resp, _full_repo_tokens(project_root)))
        resp = _mark_untrusted(resp)
        if max_tokens is not None and max_tokens > 0 and resp.get("match") is not None:
            # Same final guarantee as tricorder_detail: verify the
            # serialized total, shaving the match body on estimate drift.
            _final_budget_check(resp, resp["match"], max_tokens, project_root)
        return resp

    except Exception as e:
        log.exception(f"Error locating '{query}' in project '{project_root}': {e}")
        return {"error": f"Error locating symbol: {str(e)}"}


@mcp.tool()
async def tricorder_query(
    project_root: str,
    query: str,
    token_limit: int = 2048,
) -> Dict[str, Any]:
    """Execute a graph traversal query on the codebase.

    DSL Grammar:
        query := traversal ('|' traversal)*
        traversal := kind '(' target ')' modifiers?
        kind := "callers" | "callees" | "refs" | "defs" | "tests_for"
        target := quoted string (single or double quotes)
        modifiers := (modifier)*
        modifier := "depth=" INT | "exclude=" GLOB | "include=" GLOB
                  | "type=" ("function"|"class"|"method"|"variable") | "limit=" INT

    Examples:
        "callers('authenticate') depth=2"              # all callers up to 2 hops
        "callees('main') depth=1 exclude=tests/**"     # direct callees, skip tests
        "refs('Config') type=class limit=50"           # all references to class Config
        "tests_for('authenticate')"                   # tests that call authenticate
        "callers('foo') | callees('bar') depth=3"      # chained traversals

    Args:
        project_root: Root directory of the project (must be absolute path!)
        query: Graph query DSL string
        token_limit: Maximum tokens for response (default 2048)

    Returns:
        Dictionary with:
        - nodes: list of {name, file, line, type}
        - edges: list of {from, to, from_file, to_file, from_line, to_line, type}
          (edges traversed via a bare-name fallback also carry
          "resolution": "bare-name-fallback" — the query was qualified but the
          index only holds bare names, so homonyms may conflate)
        - token_estimate, full_repo_estimate, savings_pct
        - tier_hint (if response truncated)
        - stats: {nodes_visited, edges_traversed, bare_name_fallbacks}
    """
    # Parse query DSL
    try:
        parsed = parse_query_dsl(query)
    except ValueError as e:
        return {"error": f"Invalid query syntax: {e}"}

    if not parsed.steps:
        return {"error": "Empty query"}

    err, root_path = _validate_project_root(project_root)
    if err:
        return {"error": err}

    project_root = str(root_path)

    try:
        repo_map = _get_tricorder(project_root)

        result = repo_map.query_graph(parsed, token_limit=token_limit)
        return _mark_untrusted(result)

    except Exception as e:
        log.exception(f"Error executing graph query '{query}' on project '{project_root}': {e}")
        return {"error": f"Error executing graph query: {str(e)}"}

# --- Main Entry Point ---
def main():
    # Run the MCP server
    log.debug("Starting FastMCP server...")
    mcp.run()

if __name__ == "__main__":
    main()