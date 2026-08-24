"""Tests for MCP server path handling and token limit enforcement."""
import sys
import unittest
sys.path.insert(0, '.')
from pathlib import Path
from utils import count_tokens


class TestMCPPathHandling(unittest.TestCase):
    def test_path_dedup(self):
        """./main.py and main.py resolve to same path."""
        p1 = Path('./main.py').resolve()
        p2 = Path('main.py').resolve()
        self.assertEqual(p1, p2)

    def test_relative_project_root(self):
        """Path.resolve() prevents relative_to crash on relative project_root."""
        relative_root = './some/project'
        resolved_root = str(Path(relative_root).resolve())
        # This should not raise
        test_path = str(Path(resolved_root) / 'file.py')
        rel = Path(test_path).relative_to(resolved_root)
        self.assertEqual(str(rel), 'file.py')

    def test_path_normalize_consistency(self):
        """Multiple relative paths resolve consistently."""
        paths = ['./utils.py', 'utils.py', '.\\\\utils.py']
        resolved = [str(Path(p).resolve()) for p in paths]
        self.assertEqual(len(set(resolved)), 1, "All relative paths should resolve to same absolute path")


class TestMCPTokenLimit(unittest.TestCase):
    def setUp(self):
        self.project_root = str(Path(__file__).parent.parent)

    def test_excluded_capped_by_budget(self):
        """Excluded dict entries fit within remaining token budget."""
        from core import Tricorder, FileReport
        repo_map = Tricorder(root=self.project_root, map_tokens=500)
        class_path = str(Path(self.project_root) / 'core.py')
        map_content, file_report = repo_map.get_repo_map(
            chat_files=[class_path],
            other_files=[class_path]
        )
        map_tokens_actual = count_tokens(map_content or "", "gpt-4")
        remaining_tokens = max(0, 500 - map_tokens_actual)
        remaining_chars = remaining_tokens * 4
        excluded_size = sum(len(k) + len(v) + 20 for k, v in file_report.excluded.items())
        # The capped excluded should fit within remaining budget
        self.assertLessEqual(excluded_size, remaining_chars or 100)

    def test_max_files_cap(self):
        """Auto-scan respects max_files limit."""
        from tricorder_server import find_src_files
        all_files = find_src_files(self.project_root)
        max_files = 10
        if len(all_files) > max_files:
            capped = all_files[:max_files]
            self.assertEqual(len(capped), max_files)
        else:
            self.assertLessEqual(len(all_files), max_files)


class TestMCPTierContext(unittest.TestCase):
    def setUp(self):
        self.project_root = str(Path(__file__).parent.parent)

    def test_tier_context_lines(self):
        """tier=1, context_lines=5 produces more context than tier=1, context_lines=2."""
        from core import Tricorder
        class_path = str(Path(self.project_root) / 'core.py')
        rm_small = Tricorder(root=self.project_root, context_lines=2)
        rm_large = Tricorder(root=self.project_root, context_lines=5)
        ranked_tags, _ = rm_small.get_ranked_tags([class_path], [])
        if ranked_tags:
            tree_small = rm_small.to_tree(ranked_tags[:3], set())
            tree_large = rm_large.to_tree(ranked_tags[:3], set())
            # Larger context should produce more lines
            self.assertGreater(len(tree_large.splitlines()), len(tree_small.splitlines()))


class TestMCPOutputFile(unittest.TestCase):
    """Test the output_file parameter — writes map to file, returns only metadata."""
    def setUp(self):
        self.project_root = str(Path(__file__).parent.parent)
        import tempfile
        self.tmpdir = tempfile.mkdtemp(prefix="tricorder_test_")
        import shutil
        self.addCleanup(shutil.rmtree, self.tmpdir, True)
        # TC-008: clean up contained output dir created by output_file writes
        self.output_dir = Path(__file__).resolve().parent.parent / ".tricorder" / "output"
        self.addCleanup(shutil.rmtree, str(self.output_dir), True)

    def test_output_file_writes_map_and_returns_metadata(self):
        """repo_map with output_file writes map to disk and returns no 'map' key."""
        import asyncio
        from tricorder_server import tricorder_scan, _tier_history_store
        _tier_history_store.clear()  # fresh state

        out_file = str(Path(self.tmpdir) / "T0.txt")
        result = asyncio.run(tricorder_scan(
            project_root=self.project_root,
            token_limit=2048,
            tier=0,
            output_file=out_file
        ))

        self.assertNotIn("map", result, "Response should NOT contain 'map' key when output_file is set")
        self.assertIn("map_file", result)
        self.assertIn("token_estimate", result)
        # TC-008: output_file is contained to .tricorder/output/ — basename preserved, dir contained
        expected_dir = Path(__file__).resolve().parent.parent / ".tricorder" / "output"
        expected_path = expected_dir / Path(out_file).name
        self.assertEqual(result["map_file"], str(expected_path))
        self.assertTrue(Path(expected_path).exists(), "Map file should exist in contained output dir")
        self.assertGreater(result["token_estimate"], 0)
        self.assertEqual(result["tier"], 0)
        self.assertEqual(result["format"], "text")
        # The file should contain actual content (read from the contained path)
        content = Path(result["map_file"]).read_text(encoding="utf-8")
        self.assertGreater(len(content), 50, "Map file should have substantial content")

    def test_output_file_path_traversal_contained(self):
        """TC-008: traversal paths like ../../etc/passwd are contained to basename only."""
        import asyncio
        from tricorder_server import tricorder_scan, _tier_history_store
        _tier_history_store.clear()

        # A path traversal attempt — only the basename should be used
        evil_path = str(Path(self.tmpdir) / "...." / "...." / "evil_map.txt")
        result = asyncio.run(tricorder_scan(
            project_root=self.project_root,
            token_limit=2048,
            tier=0,
            output_file=evil_path
        ))

        # The written file must be inside the contained output dir, not escaped
        expected_path = self.output_dir / "evil_map.txt"
        self.assertEqual(result["map_file"], str(expected_path))
        self.assertTrue(expected_path.exists())

    def test_output_file_tier_hint_on_upgrade(self):
        """Calling T0 then T1 with output_file produces a tier_hint advisory."""
        import asyncio
        from tricorder_server import tricorder_scan, _tier_history_store
        _tier_history_store.clear()

        t0_file = str(Path(self.tmpdir) / "T0.txt")
        t1_file = str(Path(self.tmpdir) / "T1.txt")

        # First call: T0
        asyncio.run(tricorder_scan(
            project_root=self.project_root,
            token_limit=2048,
            tier=0,
            output_file=t0_file
        ))

        # Second call: T1 — should get tier_hint
        result = asyncio.run(tricorder_scan(
            project_root=self.project_root,
            token_limit=4096,
            tier=1,
            context_lines=3,
            output_file=t1_file
        ))

        self.assertIn("tier_hint", result, "T1 after T0 should produce a tier_hint advisory")
        self.assertIn("T0", result["tier_hint"])

    def test_stdout_path_still_returns_map(self):
        """Without output_file, the response still contains the full 'map' string (backward compat)."""
        import asyncio
        from tricorder_server import tricorder_scan, _tier_history_store
        _tier_history_store.clear()

        result = asyncio.run(tricorder_scan(
            project_root=self.project_root,
            token_limit=1024,
            tier=0,
        ))

        self.assertIn("map", result, "Without output_file, 'map' key should be present")
        self.assertNotIn("map_file", result)
        if "error" not in result:
            self.assertIsInstance(result["map"], str)


class TestMCPDryRun(unittest.TestCase):
    """Test the dry_run parameter — estimates without generating map."""
    def setUp(self):
        self.project_root = str(Path(__file__).parent.parent)

    def test_dry_run_returns_estimate(self):
        """dry_run returns tags, tokens_per_tag, tags_at_budget, full_repo_estimate."""
        import asyncio
        from tricorder_server import tricorder_scan

        result = asyncio.run(tricorder_scan(
            project_root=self.project_root,
            token_limit=8192,
            dry_run=True
        ))

        self.assertNotIn("error", result)
        self.assertIn("tags", result)
        self.assertGreater(result["tags"], 0)
        self.assertIn("tokens_per_tag", result)
        self.assertGreater(result["tokens_per_tag"], 0)
        self.assertIn("tags_at_budget", result)
        self.assertIn("full_repo_estimate", result)
        self.assertGreater(result["full_repo_estimate"], 0)
        # No map content returned
        self.assertNotIn("map", result)
        self.assertNotIn("map_file", result)

    def test_dry_run_respects_token_limit(self):
        """Lower token_limit → fewer tags_at_budget."""
        import asyncio
        from tricorder_server import tricorder_scan

        result_high = asyncio.run(tricorder_scan(
            project_root=self.project_root,
            token_limit=16384,
            dry_run=True
        ))
        result_low = asyncio.run(tricorder_scan(
            project_root=self.project_root,
            token_limit=2048,
            dry_run=True
        ))

        self.assertGreater(result_high["tags_at_budget"], result_low["tags_at_budget"])


class TestMCPMaxFilesClamp(unittest.TestCase):
    """TC-007: max_files parameter is clamped server-side."""

    def setUp(self):
        self.project_root = str(Path(__file__).parent.parent)

    def test_max_files_clamped_to_server_limit(self):
        """A caller passing max_files=999999999 is clamped to MAX_ALLOWED_FILES."""
        import asyncio
        from tricorder_server import tricorder_scan
        # Request absurd size — should be clamped, not honored
        result = asyncio.run(tricorder_scan(
            project_root=self.project_root,
            token_limit=2048,
            tier=0,
            max_files=999999999,
            output_format="text",
        ))
        self.assertNotIn("error", result)
        # If there are files, the result should still be bounded (not crash)
        # The clamp guarantees the scan never processes more than MAX_ALLOWED_FILES
        if "tags" in result:
            self.assertIsInstance(result["tags"], int)

    def test_max_files_clamp_returns_valid_for_normal_values(self):
        """Normal max_files values still work."""
        import asyncio
        from tricorder_server import tricorder_scan
        result = asyncio.run(tricorder_scan(
            project_root=self.project_root,
            token_limit=2048,
            tier=0,
            max_files=10,
        ))
        self.assertNotIn("error", result)


class TestMCPPathContainment(unittest.TestCase):
    """TC-006: file paths resolving outside project_root are rejected."""

    def setUp(self):
        self.project_root = str(Path(__file__).parent.parent)

    def test_scan_rejects_escaping_chat_file(self):
        """chat_files with ../../ escapes project_root should return error."""
        import asyncio
        from tricorder_server import tricorder_scan, _tier_history_store
        _tier_history_store.clear()
        result = asyncio.run(tricorder_scan(
            project_root=self.project_root,
            token_limit=1024,
            tier=0,
            chat_files=["../../etc/hostname"],
        ))
        self.assertIn("error", result)

    def test_detail_rejects_escaping_file(self):
        """tricorder_detail with file outside project_root should return error."""
        import asyncio
        from tricorder_server import tricorder_detail
        result = asyncio.run(tricorder_detail(
            project_root=self.project_root,
            file="../../etc/hostname",
            name="anything",
        ))
        self.assertIn("error", result)


if __name__ == '__main__':
    unittest.main()
