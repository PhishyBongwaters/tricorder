"""Tests for Tricorder.get_ranked_tags and caching."""
import sys
import os
import shutil
import tempfile
import unittest
from unittest import mock
sys.path.insert(0, '.')
from pathlib import Path
from core import Tricorder, FileReport
import cache as cache_mod


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
    # NB: the "cache lives outside the repo" invariant is asserted once, in
    # tests/test_security_hardening.py::TestTC003CacheIsolation (TC-003).
    def test_cache_identity_is_content_derived(self):
        a = Tricorder(root='/tmp/test_root')._cache_dir()
        b = Tricorder(root='/tmp/other_root')._cache_dir()
        self.assertNotEqual(a, b)

    def test_capture_change_busts_tags_cache(self):
        # Regression: the python-tags.scm argument-ref capture must not be
        # masked by a stale per-file cache entry written by an older
        # extractor. database.py says "bump on ANY capture change" and the
        # cache directory is keyed by EXTRACTOR_VERSION, so an entry
        # written under an older version is never served.
        tmp = Path(tempfile.mkdtemp(prefix="cache_capture_"))
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        f = tmp / "reg.py"
        f.write_text(
            "handlers = {}\n"
            "handlers.setdefault(ValueError, authenticate)\n",
            encoding="utf-8",
        )
        # Simulate the old (v2) extractor's cache entry: same file, same
        # fingerprint, but the pre-argument-ref tag set.
        with mock.patch.object(cache_mod, "EXTRACTOR_VERSION", 2):
            tc_old = Tricorder(root=str(tmp), use_db=False, verbose=False)
            stale = [t for t in tc_old.get_tags_raw(str(f), "reg.py")
                     if not (t.kind == "ref"
                             and t.name in ("ValueError", "authenticate"))]
            self.assertFalse(
                any(t.kind == "ref" and t.name == "authenticate"
                    for t in stale),
                "test setup: stale entry must lack the argument refs",
            )
            fp = tc_old._file_fingerprint(str(f))
            tc_old.TAGS_CACHE[str(f)] = {"fp": fp, "data": stale}
        # The current extractor must not serve the v2 entry: the
        # argument-position ref has to come back from a fresh parse.
        tc = Tricorder(root=str(tmp), use_db=False, verbose=False)
        tags = tc.get_tags(str(f), "reg.py")
        self.assertTrue(
            any(t.kind == "ref" and t.name == "authenticate" for t in tags),
            "stale pre-capture-change cache entry must not mask the new "
            "argument-position refs",
        )


class TestTricorderT1Context(unittest.TestCase):
    def setUp(self):
        self.project_root = str(Path(__file__).parent.parent)

    def test_t0_no_context(self):
        repo_map = Tricorder(root=self.project_root, context_lines=0)
        self.assertEqual(repo_map.context_lines, 0)
        class_path = str(Path(self.project_root) / 'core.py')
        ranked_tags, _ = repo_map.get_ranked_tags([class_path], [])
        self.assertTrue(ranked_tags, "fixture must yield tags for the assertions below")
        if ranked_tags:
            tree = repo_map.to_tree(ranked_tags[:5], set())
            # T0 should only show definition lines, no surrounding context
            self.assertIn('core.py', tree)

    def test_tier_headers_group_files(self):
        repo_map = Tricorder(root=self.project_root, context_lines=0)
        files = [str(Path(self.project_root) / f) for f in ['core.py', 'utils.py']]
        ranked_tags, _ = repo_map.get_ranked_tags(files, [])
        if ranked_tags:
            # Use the full ranked list: with DB-by-default + real PageRank the
            # relative order of core.py vs utils.py can vary, so don't slice so
            # tight that one legitimately-ranked file falls out of the window.
            tree = repo_map.to_tree(ranked_tags, set())
            self.assertIn('root/', tree)
            self.assertIn('core.py', tree)
            self.assertIn('utils.py', tree)

    def test_context_lines_clamped(self):
        repo_map = Tricorder(root=self.project_root, context_lines=100)
        self.assertEqual(repo_map.context_lines, 100)
        class_path = str(Path(self.project_root) / 'core.py')
        ranked_tags, _ = repo_map.get_ranked_tags([class_path], [])
        self.assertTrue(ranked_tags, "fixture must yield tags for the assertions below")
        if ranked_tags:
            tree = repo_map.to_tree(ranked_tags[:5], set())
            # Should not crash even with large context_lines (clamped to file boundaries)
            self.assertIsNotNone(tree)

    def test_rank_line_skipped_when_uniform(self):
        """PR-3: rank line omitted when all files share the same rank."""
        repo_map = Tricorder(root=self.project_root, context_lines=0)
        class_path = str(Path(self.project_root) / 'core.py')
        ranked_tags, _ = repo_map.get_ranked_tags([class_path], [])
        self.assertTrue(ranked_tags, "fixture must yield tags for the assertions below")
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
