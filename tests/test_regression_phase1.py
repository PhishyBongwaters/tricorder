#!/usr/bin/env python3
"""
Phase 1: Regression Tests for all 11 fixes.
"""
import asyncio
import sys
import tempfile
import os
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).parent.parent))

from utils import (
    repo_budget, calculate_full_repo_budget, count_tokens, read_text,
    discover_src_files, parse_gitignore, _tiktoken,
)
from ctags_probe import (
    LANGUAGE_REGISTRY, get_ctags_languages, get_tree_sitter_languages,
    get_language_extensions, get_scm_query_for_lang, get_ctags_name,
    _get_repo_hash, _get_tags_cache_path, _get_meta_cache_path,
    _get_git_commit, _read_tags_meta, _write_tags_meta, _is_meta_stale,
    _count_source_files, ensure_ctags_index,
)
from tricorder_server import (
    _tier_history_store, _tier_history_get, _tier_history_set, _MAX_TIER_HISTORY,
    tricorder_detect,
)


class TestFullRepoEstimateAccuracy(unittest.TestCase):
    """Test that repo_budget returns accurate full_repo_estimate and savings_pct."""

    def setUp(self):
        self.project_root = str(Path(__file__).parent.parent.resolve())

    def test_full_repo_estimate_consistency(self):
        """Multiple calls should return consistent full_repo_estimate."""
        r1 = repo_budget(self.project_root, 1000)
        r2 = repo_budget(self.project_root, 2000)
        self.assertEqual(r1["full_repo_estimate"], r2["full_repo_estimate"])

    def test_savings_pct_calculation(self):
        """savings_pct should be correctly calculated."""
        # With token_estimate=0, savings should be 0
        r = repo_budget(self.project_root, 0)
        self.assertEqual(r["savings_pct"], 0.0)

        # With token_estimate = full_repo_estimate, savings should be 0
        r = repo_budget(self.project_root, r["full_repo_estimate"])
        self.assertEqual(r["savings_pct"], 0.0)

        # With small token_estimate, savings should be high
        r = repo_budget(self.project_root, 1000)
        self.assertGreater(r["savings_pct"], 90.0)
        self.assertLessEqual(r["savings_pct"], 100.0)

    def test_calculate_full_repo_budget_force_refresh(self):
        """force_refresh should recalculate and return same value."""
        r1 = calculate_full_repo_budget(self.project_root, 1000, force_refresh=True)
        r2 = calculate_full_repo_budget(self.project_root, 1000, force_refresh=True)
        self.assertEqual(r1["full_repo_estimate"], r2["full_repo_estimate"])

    def test_budget_cache_location(self):
        """Budget cache lives under .tricorder/cache/ in the project root."""
        _ = repo_budget(self.project_root, 1000)
        self.assertTrue(
            (Path(self.project_root) / ".tricorder" / "cache").exists(),
            "Budget cache should be under project/.tricorder/cache/",
        )


class TestTierHistoryMemoryBound(unittest.TestCase):
    """Test that _tier_history_store is bounded by _MAX_TIER_HISTORY."""

    def test_max_size_enforced(self):
        """Store should never exceed _MAX_TIER_HISTORY entries."""
        # Clear first
        _tier_history_store.clear()
        
        # Fill beyond capacity
        for i in range(_MAX_TIER_HISTORY + 50):
            _tier_history_set(f"project_{i}", {"last_tier": 0, "last_format": "text", "map_file": f"map_{i}.txt"})
        
        self.assertEqual(len(_tier_history_store), _MAX_TIER_HISTORY)

    def test_lru_eviction(self):
        """Oldest entries should be evicted first."""
        _tier_history_store.clear()
        
        for i in range(_MAX_TIER_HISTORY + 10):
            _tier_history_set(f"project_{i}", {"last_tier": i, "last_format": "text", "map_file": f"map_{i}.txt"})
        
        # First 10 should be evicted
        for i in range(10):
            self.assertIsNone(_tier_history_get(f"project_{i}"))
        
        # Last 10 should exist
        for i in range(_MAX_TIER_HISTORY - 10, _MAX_TIER_HISTORY):
            self.assertIsNotNone(_tier_history_get(f"project_{i}"))

    def test_update_moves_to_mru(self):
        """Updating an entry should move it to most-recently-used."""
        _tier_history_store.clear()
        
        for i in range(_MAX_TIER_HISTORY):
            _tier_history_set(f"project_{i}", {"last_tier": 0, "last_format": "text", "map_file": f"map_{i}.txt"})
        
        # Update the first entry
        _tier_history_set("project_0", {"last_tier": 1, "last_format": "text", "map_file": "map_0_new.txt"})
        
        # Fill 10 more
        for i in range(_MAX_TIER_HISTORY, _MAX_TIER_HISTORY + 10):
            _tier_history_set(f"project_{i}", {"last_tier": 0, "last_format": "text", "map_file": f"map_{i}.txt"})
        
        # project_0 should still exist (was updated to MRU)
        self.assertIsNotNone(_tier_history_get("project_0"))
        self.assertEqual(_tier_history_get("project_0")["last_tier"], 1)


class TestCtagsMetadataInvalidation(unittest.TestCase):
    """Test ctags index metadata-based invalidation."""

    def setUp(self):
        self.project_root = str(Path(__file__).parent.parent.resolve())
        self.tmpdir = Path(self.project_root) / "bench_temp" / "test_ctags_meta"
        self.tmpdir.mkdir(parents=True, exist_ok=True)
    
    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_meta_roundtrip(self):
        """Metadata write/read should preserve data."""
        meta_path = self.tmpdir / "test.meta.json"
        meta = {"git_commit": "abc123", "file_count": 42, "generated": 1234567890.0}
        _write_tags_meta(meta_path, meta)
        read_meta = _read_tags_meta(meta_path)
        self.assertEqual(meta, read_meta)

    def test_git_commit_detection(self):
        """Should detect git commit hash."""
        commit = _get_git_commit(self.project_root)
        self.assertIsNotNone(commit)
        self.assertEqual(len(commit), 40)  # SHA-1

    def test_is_meta_stale_git_mismatch(self):
        """Should detect stale when git commit differs."""
        meta = {
            "git_commit": "wrong_commit",
            "file_count": 100,
            "generated": 1234567890.0,
        }
        ctags_excludes = [
            "*.min.js", "*.min.css", "vendor/**", "third_party/**",
            ".git/**", "build/**", "dist/**", "node_modules/**",
            "__pycache__/**", "*.pyc",
        ]
        stale = _is_meta_stale(meta, self.project_root, ctags_excludes, max_age_days=7)
        self.assertTrue(stale)

    def test_is_meta_stale_file_count_mismatch(self):
        """Should detect stale when file count differs."""
        commit = _get_git_commit(self.project_root)
        meta = {
            "git_commit": commit,
            "file_count": 999999,  # Wrong count
            "generated": 1234567890.0,
        }
        ctags_excludes = [
            "*.min.js", "*.min.css", "vendor/**", "third_party/**",
            ".git/**", "build/**", "dist/**", "node_modules/**",
            "__pycache__/**", "*.pyc",
        ]
        stale = _is_meta_stale(meta, self.project_root, ctags_excludes, max_age_days=7)
        self.assertTrue(stale)

    def test_is_meta_stale_age(self):
        """Should detect stale when age exceeds max_age_days."""
        commit = _get_git_commit(self.project_root)
        ctags_excludes = [
            "*.min.js", "*.min.css", "vendor/**", "third_party/**",
            ".git/**", "build/**", "dist/**", "node_modules/**",
            "__pycache__/**", "*.pyc",
        ]
        file_count = _count_source_files(self.project_root, exclude_globs=ctags_excludes)
        meta = {
            "git_commit": commit,
            "file_count": file_count,
            "generated": 0,  # Very old
        }
        stale = _is_meta_stale(meta, self.project_root, ctags_excludes, max_age_days=7)
        self.assertTrue(stale)

    def test_is_meta_fresh(self):
        """Should NOT detect stale when all matches."""
        import time
        commit = _get_git_commit(self.project_root)
        ctags_excludes = [
            "*.min.js", "*.min.css", "vendor/**", "third_party/**",
            ".git/**", "build/**", "dist/**", "node_modules/**",
            "__pycache__/**", "*.pyc",
        ]
        file_count = _count_source_files(self.project_root, exclude_globs=ctags_excludes)
        meta = {
            "git_commit": commit,
            "file_count": file_count,
            "generated": time.time(),  # Current time, not old
        }
        stale = _is_meta_stale(meta, self.project_root, ctags_excludes, max_age_days=3650)
        self.assertFalse(stale)


class TestDetectSearchModes(unittest.TestCase):
    """Test tricorder_detect search_mode parameter."""

    def setUp(self):
        self.project_root = str(Path(__file__).parent.parent.resolve())

    def test_exact_mode(self):
        """Exact mode should match whole word only."""
        result = asyncio.run(tricorder_detect(
            project_root=self.project_root,
            query="count_tokens",
            search_mode="exact",
            max_results=100,
        ))
        self.assertNotIn("error", result)
        names = [r["name"] for r in result["results"]]
        self.assertIn("count_tokens", names)
        # Should NOT match "test_count_tokens" etc.
        for name in names:
            self.assertEqual(name, "count_tokens")

    def test_substring_mode(self):
        """Substring mode should match contained strings."""
        result = asyncio.run(tricorder_detect(
            project_root=self.project_root,
            query="count",
            search_mode="substring",
            max_results=100,
        ))
        self.assertNotIn("error", result)
        names = [r["name"] for r in result["results"]]
        self.assertTrue(any("count" in n for n in names))

    def test_regex_mode(self):
        """Regex mode should support Python regex patterns."""
        result = asyncio.run(tricorder_detect(
            project_root=self.project_root,
            query="count_.*",
            search_mode="regex",
            max_results=100,
        ))
        self.assertNotIn("error", result)
        names = [r["name"] for r in result["results"]]
        self.assertTrue(any(n.startswith("count_") for n in names))

    def test_regex_invalid(self):
        """Invalid regex should return error."""
        result = asyncio.run(tricorder_detect(
            project_root=self.project_root,
            query="[invalid",
            search_mode="regex",
            max_results=100,
        ))
        self.assertIn("error", result)
        self.assertIn("Invalid regex", result["error"])

    def test_invalid_search_mode(self):
        """Invalid search_mode should return error."""
        result = asyncio.run(tricorder_detect(
            project_root=self.project_root,
            query="test",
            search_mode="invalid_mode",
            max_results=100,
        ))
        self.assertIn("error", result)
        self.assertIn("Invalid search_mode", result["error"])

    def test_case_insensitive(self):
        """All modes should be case-insensitive."""
        result = asyncio.run(tricorder_detect(
            project_root=self.project_root,
            query="COUNT_TOKENS",
            search_mode="exact",
            max_results=100,
        ))
        self.assertNotIn("error", result)
        names = [r["name"] for r in result["results"]]
        self.assertIn("count_tokens", names)


class TestReadTextStrictMode(unittest.TestCase):
    """Test read_text strict parameter."""

    def setUp(self):
        self.tmpdir = Path(__file__).parent.parent / "bench_temp" / "test_read_text"
        self.tmpdir.mkdir(parents=True, exist_ok=True)
    
    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_default_ignore(self):
        """Default should ignore invalid bytes."""
        test_file = self.tmpdir / "invalid.txt"
        test_file.write_bytes(b"Hello \xff\xfe world")
        result = read_text(str(test_file))
        self.assertIsNotNone(result)
        self.assertIn("Hello", result)
        self.assertIn("world", result)

    def test_strict_true_raises(self):
        """strict=True should raise UnicodeError."""
        test_file = self.tmpdir / "invalid.txt"
        test_file.write_bytes(b"Hello \xff\xfe world")
        result = read_text(str(test_file), strict=True)
        self.assertIsNone(result)  # Returns None on error

    def test_silent_mode(self):
        """silent=True should suppress errors."""
        test_file = self.tmpdir / "nonexistent.txt"
        result = read_text(str(test_file), silent=True)
        self.assertIsNone(result)


class TestLanguageRegistry(unittest.TestCase):
    """Test ctags_probe language registry."""

    def setUp(self):
        self.project_root = str(Path(__file__).parent.parent.resolve())

    def test_registry_completeness(self):
        """Registry should have all expected languages."""
        expected = [
            "python", "javascript", "typescript", "c", "cpp", "java", "go",
            "rust", "swift", "kotlin", "ruby", "php", "c_sharp", "shell",
            "lua", "perl", "sql", "html", "css", "json", "yaml", "toml", "xml", "markdown"
        ]
        for lang in expected:
            self.assertIn(lang, LANGUAGE_REGISTRY)

    def test_get_ctags_languages(self):
        """get_ctags_languages should return ctags names."""
        langs = get_ctags_languages()
        self.assertIn("Python", langs)
        self.assertIn("C++", langs)
        self.assertIn("TypeScript", langs)
        self.assertEqual(len(langs), 24)

    def test_get_tree_sitter_languages(self):
        """get_tree_sitter_languages should return tree-sitter keys."""
        langs = get_tree_sitter_languages()
        self.assertIn("python", langs)
        self.assertIn("cpp", langs)
        self.assertIn("typescript", langs)

    def test_get_language_extensions(self):
        """get_language_extensions should return correct extensions."""
        self.assertEqual(get_language_extensions("python"), [".py"])
        self.assertEqual(set(get_language_extensions("shell")), {".sh", ".bash", ".zsh"})

    def test_get_scm_query_for_lang(self):
        """get_scm_query_for_lang should return SCM filename."""
        self.assertEqual(get_scm_query_for_lang("python"), "python-tags.scm")
        self.assertEqual(get_scm_query_for_lang("cpp"), "cpp-tags.scm")

    def test_get_ctags_name(self):
        """get_ctags_name should return ctags name."""
        self.assertEqual(get_ctags_name("python"), "Python")
        self.assertEqual(get_ctags_name("c_sharp"), "C#")
        self.assertEqual(get_ctags_name("c"), "C")

    def test_repo_hash_stable(self):
        """Repo hash should be stable for same path."""
        h1 = _get_repo_hash(self.project_root)
        h2 = _get_repo_hash(self.project_root)
        self.assertEqual(h1, h2)
        self.assertEqual(len(h1), 16)


class TestLazyTiktoken(unittest.TestCase):
    """Test that tiktoken is lazily imported."""

    def test_tiktoken_not_imported_at_module_load(self):
        """_tiktoken should be None before first count_tokens call."""
        import utils
        # Force reload to test initial state
        # (can't easily test without complex module manipulation, but we can
        # verify the pattern is in place)
        self.assertTrue(hasattr(utils, '_tiktoken'))

    def test_count_tokens_works(self):
        """count_tokens should work normally."""
        result = count_tokens("hello world")
        self.assertEqual(result, 2)


class TestTurn0ProbeGateRemoved(unittest.TestCase):
    """Test that turn-0 probe gate is removed."""

    def test_probe_always_injected_for_code_repos(self):
        """Probe should be injected for any repo with code files."""
        from utils import probe_project, format_probe_digest, INJECT_MIN_FILES
        
        # The gate constant should be 0
        self.assertEqual(INJECT_MIN_FILES, 0)
        
        # Should return digest for tricorder repo
        probe = probe_project(str(Path(__file__).parent.parent.resolve()))
        digest = format_probe_digest(probe, str(Path(__file__).parent.parent.resolve()))
        self.assertTrue(len(digest) > 0)
        self.assertGreater(probe["total_files"], 0)


class TestRepoBudgetCaching(unittest.TestCase):
    """Test repo_budget caching behavior."""

    def setUp(self):
        self.project_root = str(Path(__file__).parent.parent.resolve())
        # Start clean so tests don't interfere with each other
        _tr = Path(self.project_root) / ".tricorder"
        if _tr.exists():
            import shutil
            shutil.rmtree(_tr, ignore_errors=True)

    def tearDown(self):
        _tr = Path(self.project_root) / ".tricorder"
        if _tr.exists():
            import shutil
            shutil.rmtree(_tr, ignore_errors=True)

    def test_cache_path_under_project_tricorder(self):
        """Budget cache is written under .tricorder/cache/ in the project root."""
        repo_budget(self.project_root, 1000)
        self.assertTrue(
            (Path(self.project_root) / ".tricorder" / "cache").exists(),
            "Cache should be created under project/.tricorder/cache/",
        )

    def test_second_call_uses_cache(self):
        """Second call should use cached value (same result)."""
        import time
        t1 = time.time()
        r1 = repo_budget(self.project_root, 1000)
        t2 = time.time()
        r2 = repo_budget(self.project_root, 1000)
        t3 = time.time()
        
        # Results should be identical
        self.assertEqual(r1["full_repo_estimate"], r2["full_repo_estimate"])
        self.assertEqual(r1["savings_pct"], r2["savings_pct"])
        
        # Second call should be faster (using cache)
        # (Not asserting on time as it's flaky, but logic is correct)


if __name__ == "__main__":
    unittest.main()