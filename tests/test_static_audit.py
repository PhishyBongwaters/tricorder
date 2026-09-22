"""Red-first regression tests for the independent static audit findings.

1. render._cached_tree_context validated its cache with float st_mtime.
   Two edits ~1ns apart map to the SAME float (double ulp at this epoch is
   ~238ns), so a same-second same-size edit could render stale snippet
   lines from the TreeContext built from old code.
2. parser.get_tags_raw's `except ImportError` branch raised
   GrepAstNotAvailableError, which was never imported into parser.py
   (circular with core at top level) -> latent NameError.
"""
import os
import sys
import types
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from render import _cached_tree_context


class _FakeSelf:
    def __init__(self):
        self.tree_context_cache = {}


def _double_ulp_seconds():
    # ulp of a double near the current epoch (~1.78e9 s)
    import math
    return math.ulp(1.78e9)


def test_cached_tree_context_invalidated_on_sub_float_ulp_edit(tmp_path):
    f = tmp_path / "a.py"
    f.write_text("x = 1\n")  # 6 bytes
    absf = str(f)
    st0 = os.stat(absf)
    ns0 = st0.st_mtime_ns

    self = _FakeSelf()
    tc1 = _cached_tree_context(self, absf, "a.py", "x = 1\n", [0])

    # Same-size edit, mtime moved by 1ns -- below float(double) resolution.
    f.write_text("x = 2\n")
    ns1 = ns0 + 1
    os.utime(absf, ns=(st0.st_atime_ns, ns1))
    if os.stat(absf).st_mtime_ns != ns1:
        pytest.skip("OS/filesystem cannot represent 1ns mtime steps")
    assert float(ns1) / 1e9 == float(ns0) / 1e9, (
        "test premise broken: 1ns step changed the float mtime on this platform"
    )

    tc2 = _cached_tree_context(self, absf, "a.py", "x = 2\n", [0])
    assert tc2 is not tc1, (
        "stale TreeContext: cache key did not notice a sub-float-ulp mtime change"
    )


def test_grep_ast_import_error_raises_named_error():
    from parser import ParserMixin
    from core import GrepAstNotAvailableError

    dummy = types.SimpleNamespace()
    with __import__("unittest.mock", fromlist=["patch"]).patch.dict(
        sys.modules, {"grep_ast.tsl": None}
    ):
        try:
            ParserMixin.get_tags_raw(dummy, "a.py", "a.py")
        except GrepAstNotAvailableError:
            return  # expected
        except NameError as e:
            raise AssertionError(f"latent NameError in ImportError branch: {e}")
    raise AssertionError("expected GrepAstNotAvailableError, nothing raised")


def test_discover_src_files_clears_stale_warning(tmp_path):
    """A clean scan must not inherit a previous scan's limit warning.

    _last_scan_report is process-global and write-once; without clearing,
    scan B's response would wrongly claim a partial scan after scan A hit
    a limit. Threaded path already clears; serial path did not.
    """
    import os as _os
    from unittest.mock import patch
    from utils import discover_src_files

    (tmp_path / "a.py").write_text("x = 1\n")
    for workers in ("1", "2"):
        report = {"warning": "stale warning from previous scan"}
        with patch.dict(_os.environ, {"TRICORDER_WALK_WORKERS": workers}):
            discover_src_files(str(tmp_path), report=report)
        assert "warning" not in report, (
            f"stale warning survived a clean scan (workers={workers})"
        )


def test_clean_snapshot_wins_over_clobbered_global():
    """A clean-scan snapshot (None) must beat the process-global fallback.

    Otherwise an interleaved scan for another root that hit a limit would
    have its warning attached to this clean scan's response — the race
    round 17's snapshot was meant to close, re-entering via the fallback.
    """
    import tricorder_server as srv

    srv._last_scan_report.clear()
    srv._last_scan_report["warning"] = "stale warning from another root's scan"
    try:
        resp = srv._attach_scan_warning({}, warning=None)
        assert "scan_warning" not in resp, (
            f"stale global warning leaked into a clean scan: {resp.get('scan_warning')!r}"
        )
    finally:
        srv._last_scan_report.clear()


def test_no_discovery_means_no_warning():
    """other_files path: no discovery ran, so no warning may attach."""
    import tricorder_server as srv

    srv._last_scan_report.clear()
    srv._last_scan_report["warning"] = "stale warning from another root's scan"
    try:
        # tricorder_scan sets scan_warning=None explicitly when other_files
        # are supplied (no discovery runs for that call).
        resp = srv._attach_scan_warning({}, warning=None)
        assert "scan_warning" not in resp
    finally:
        srv._last_scan_report.clear()


def test_legacy_global_fallback_preserved():
    """Omitting `warning` keeps the legacy global fallback (backward compat)."""
    import tricorder_server as srv

    srv._last_scan_report.clear()
    srv._last_scan_report["warning"] = "limit hit"
    try:
        resp = srv._attach_scan_warning({})
        assert resp.get("scan_warning") == "limit hit"
    finally:
        srv._last_scan_report.clear()


def test_explicit_warning_attaches():
    import tricorder_server as srv

    resp = srv._attach_scan_warning({}, warning="limit hit")
    assert resp.get("scan_warning") == "limit hit"
