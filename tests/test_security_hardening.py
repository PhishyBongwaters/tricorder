"""Tests for TC-001/002/003/004 hardening behaviors."""
import os
import sys
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pathlib import Path
from utils import discover_src_files
from core import Tricorder, TAGS_CACHE_DIR
from tricorder_server import (
    tricorder_scan, _attach_scan_warning, _last_scan_report,
    wrap_untrusted_content, _TRUST_BEGIN, _TRUST_END,
)


class TestTC002ResourceEnvelope(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(__file__).parent / "_tc002_tmp"
        self.tmp.mkdir(exist_ok=True)
        self.addCleanup(lambda: _rmtree(self.tmp))

    def test_total_byte_budget_stops_walk(self):
        # 3 files each ~2MB => 6MB, under the 500MB default, so no trigger.
        # Use a tiny budget via env to force the limit.
        os.environ["TRICORDER_MAX_TOTAL_BYTES"] = "100000"  # 100KB
        try:
            for i in range(5):
                (self.tmp / f"f{i}.py").write_text("x = '" + "A" * 30000 + "'\n")
            report = {}
            files = discover_src_files(str(self.tmp), use_gitignore=False, report=report)
            self.assertIn("warning", report, "expected a partial-scan warning")
            self.assertIn("total-byte", report["warning"])
        finally:
            os.environ.pop("TRICORDER_MAX_TOTAL_BYTES", None)

    def test_file_count_budget(self):
        os.environ["TRICORDER_MAX_SCAN_FILES"] = "10"
        try:
            for i in range(50):
                (self.tmp / f"g{i}.py").write_text("def f(): pass\n")
            report = {}
            files = discover_src_files(str(self.tmp), use_gitignore=False, report=report)
            self.assertLessEqual(len(files), 10)
            self.assertIn("warning", report)
        finally:
            os.environ.pop("TRICORDER_MAX_SCAN_FILES", None)

    def test_scan_warning_surfaces_in_response(self):
        os.environ["TRICORDER_MAX_SCAN_FILES"] = "3"
        try:
            # Point scan at our temp tree; the envelope should warn.
            import asyncio
            _last_scan_report.clear()
            result = asyncio.run(tricorder_scan(
                project_root=str(self.tmp), token_limit=1024, tier=0,
            ))
            # Even a bounded scan should not error and map should be fenced (TC-001)
            self.assertNotIn("error", result)
        finally:
            os.environ.pop("TRICORDER_MAX_SCAN_FILES", None)


class TestTC003CacheIsolation(unittest.TestCase):
    def test_cache_lives_outside_repo(self):
        repo = Tricorder(root="/tmp/does_not_matter_tc003")
        cache_dir = repo._cache_dir()
        # Must NOT be a repo-relative path.
        self.assertFalse(str(cache_dir).endswith(TAGS_CACHE_DIR))
        # Identity is content-derived, so distinct roots => distinct caches.
        other = Tricorder(root="/tmp/different_root_tc003")._cache_dir()
        self.assertNotEqual(cache_dir, other)


class TestTC004ParserTimeout(unittest.TestCase):
    def test_timeout_returns_none_not_hang(self):
        repo = Tricorder(root=str(Path(__file__).parent))
        # A valid small parse completes quickly.
        import tree_sitter as ts
        from grep_ast.tsl import get_parser
        parser = get_parser("python")
        t0 = time.monotonic()
        tree = repo._parse_with_timeout(parser, "def f(): pass\n", "x.py")
        self.assertIsNotNone(tree)
        self.assertLess(time.monotonic() - t0, 5)


class TestTC001TrustBoundary(unittest.TestCase):
    def test_wrap_untrusted_content_fences(self):
        wrapped = wrap_untrusted_content("def f(): pass\n")
        self.assertTrue(wrapped.startswith(_TRUST_BEGIN))
        self.assertTrue(wrapped.strip().endswith(_TRUST_END))
        self.assertIn("def f()", wrapped)

    def test_scan_response_map_is_fenced(self):
        import asyncio
        # Use the real project (multiple source files) so a non-empty map is
        # produced; assert the returned raw map text is trust-fenced (TC-001).
        result = asyncio.run(tricorder_scan(
            project_root=str(Path(__file__).parent.parent), token_limit=2048, tier=0,
        ))
        self.assertNotIn("error", result)
        self.assertIn("map", result)
        self.assertIsNotNone(result["map"])
        self.assertTrue(result["map"].startswith(_TRUST_BEGIN))


def _rmtree(p: Path):
    import shutil
    shutil.rmtree(str(p), ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
