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
