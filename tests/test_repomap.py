"""Tests for Tricorder.get_ranked_tags and caching."""
import sys
import os
import unittest
sys.path.insert(0, '.')
from pathlib import Path
from core import Tricorder, FileReport, TAGS_CACHE_DIR


class TestTricorderRankedTags(unittest.TestCase):
    def setUp(self):
        self.project_root = str(Path(__file__).parent.parent)

    def test_get_ranked_tags_empty(self):
        repo_map = Tricorder(root=self.project_root)
        ranked_tags, file_report = repo_map.get_ranked_tags([], [])
        self.assertEqual(ranked_tags, [])
        self.assertIsInstance(file_report, FileReport)
        self.assertEqual(file_report.definition_matches, 0)
        self.assertEqual(file_report.reference_matches, 0)

    def test_get_ranked_tags_single_file(self):
        repo_map = Tricorder(root=self.project_root)
        # core.py has class definitions tree-sitter can find
        class_path = str(Path(self.project_root) / 'core.py')
        ranked_tags, file_report = repo_map.get_ranked_tags([class_path], [])
        self.assertIsInstance(ranked_tags, list)
        self.assertGreater(len(ranked_tags), 0, "Should find at least one tag in core.py")
        self.assertIsInstance(file_report, FileReport)

    def test_get_ranked_tags_excludes(self):
        repo_map = Tricorder(root=self.project_root)
        # Pass a non-existent file — gets resolved to absolute, excluded
        ranked_tags, file_report = repo_map.get_ranked_tags(
            ['/nonexistent/file.py'],
            []
        )
        self.assertEqual(ranked_tags, [])
        # Path gets resolved to absolute on Windows
        self.assertEqual(len(file_report.excluded), 1)
        excluded_path = list(file_report.excluded.keys())[0]
        self.assertIn('nonexistent', excluded_path)


class TestTricorderCache(unittest.TestCase):
    def test_cache_dir_is_relative(self):
        self.assertFalse(os.path.isabs(TAGS_CACHE_DIR))
        self.assertNotIn(os.getcwd(), TAGS_CACHE_DIR)

    def test_cache_resolves_correctly(self):
        root = '/tmp/test_root'
        resolved = Path(root) / TAGS_CACHE_DIR
        resolved_str = os.path.normpath(str(resolved))
        self.assertIn('.repomap.tags.cache.v1', resolved_str)


class TestTricorderT1Context(unittest.TestCase):
    def setUp(self):
        self.project_root = str(Path(__file__).parent.parent)

    def test_t0_no_context(self):
        repo_map = Tricorder(root=self.project_root, context_lines=0)
        self.assertEqual(repo_map.context_lines, 0)
        class_path = str(Path(self.project_root) / 'core.py')
        ranked_tags, _ = repo_map.get_ranked_tags([class_path], [])
        if ranked_tags:
            tree = repo_map.to_tree(ranked_tags[:5], set())
            # T0 should only show definition lines, no surrounding context
            self.assertIn('core.py', tree)

    def test_t1_with_context(self):
        repo_map = Tricorder(root=self.project_root, context_lines=3)
        self.assertEqual(repo_map.context_lines, 3)
        class_path = str(Path(self.project_root) / 'core.py')
        ranked_tags, _ = repo_map.get_ranked_tags([class_path], [])
        if ranked_tags:
            tree = repo_map.to_tree(ranked_tags[:5], set())
            # T1 should show definition + surrounding lines
            self.assertIn('core.py', tree)

    def test_context_lines_clamped(self):
        repo_map = Tricorder(root=self.project_root, context_lines=100)
        self.assertEqual(repo_map.context_lines, 100)
        class_path = str(Path(self.project_root) / 'core.py')
        ranked_tags, _ = repo_map.get_ranked_tags([class_path], [])
        if ranked_tags:
            tree = repo_map.to_tree(ranked_tags[:5], set())
            # Should not crash even with large context_lines (clamped to file boundaries)
            self.assertIsNotNone(tree)

    def test_rank_line_skipped_when_uniform(self):
        """PR-3: rank line omitted when all files share the same rank."""
        repo_map = Tricorder(root=self.project_root, context_lines=0)
        class_path = str(Path(self.project_root) / 'core.py')
        ranked_tags, _ = repo_map.get_ranked_tags([class_path], [])
        if ranked_tags:
            tree = repo_map.to_tree(ranked_tags[:5], set())
            self.assertNotIn('(Rank value:', tree)

    def test_untagged_skipped_in_t1(self):
        """PR-3: untagged section omitted in T1 mode (context shows imports)."""
        repo_map = Tricorder(root=self.project_root, context_lines=3)
        all_files = [str(Path(self.project_root) / f) for f in ['utils.py', 'importance.py', 'scm.py', 'core.py']]
        ranked_tags, file_report = repo_map.get_ranked_tags(all_files, [])
        tree = repo_map.to_tree(ranked_tags[:5], set(), file_report.untagged_files)
        self.assertNotIn('Other files:', tree)


if __name__ == '__main__':
    unittest.main()
