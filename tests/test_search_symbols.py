"""Tests for search_symbols MCP tool (Milestone 2)."""
import asyncio
import sys
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from repomap_server import search_symbols


class TestSearchSymbols(unittest.TestCase):
    def setUp(self):
        self.project_root = str(Path(__file__).parent.parent.resolve())

    def test_name_only(self):
        """Name-only search finds the symbol."""
        result = asyncio.run(search_symbols(
            project_root=self.project_root, query="count_tokens"
        ))
        self.assertNotIn("error", result)
        names = [s["name"] for s in result["symbols"]]
        self.assertIn("count_tokens", names)

    def test_type_only(self):
        """Type-only search returns only matching types."""
        result = asyncio.run(search_symbols(
            project_root=self.project_root, query="", type="function"
        ))
        self.assertNotIn("error", result)
        for s in result["symbols"]:
            self.assertEqual(s["type"], "function")
        self.assertGreater(len(result["symbols"]), 0)

    def test_combined_filters(self):
        """Combined query+type+file filters work with AND logic."""
        result = asyncio.run(search_symbols(
            project_root=self.project_root,
            query="map",
            type="function",
            file="repomap"
        ))
        self.assertNotIn("error", result)
        for s in result["symbols"]:
            self.assertIn("map", s["name"].lower())
            self.assertEqual(s["type"], "function")
            self.assertIn("repomap", s["file"].lower())

    def test_limit_respected(self):
        """limit=3 returns at most 3 results."""
        result = asyncio.run(search_symbols(
            project_root=self.project_root, query="", limit=3
        ))
        self.assertNotIn("error", result)
        self.assertLessEqual(len(result["symbols"]), 3)

    def test_limit_cap(self):
        """limit > 200 is capped at 200."""
        result = asyncio.run(search_symbols(
            project_root=self.project_root, query="", limit=999
        ))
        self.assertNotIn("error", result)
        self.assertLessEqual(len(result["symbols"]), 200)

    def test_all_fields_present(self):
        """Every symbol record has all 9 required fields."""
        result = asyncio.run(search_symbols(
            project_root=self.project_root, query="count_tokens"
        ))
        self.assertNotIn("error", result)
        required = {"name", "type", "file", "line", "end_line",
                     "signature", "docstring", "language", "kind"}
        for s in result["symbols"]:
            missing = required - set(s.keys())
            self.assertFalse(missing, f"Missing: {missing} in {s['name']}")

    def test_performance(self):
        """Full scan returns in <2s."""
        start = time.time()
        result = asyncio.run(search_symbols(
            project_root=self.project_root, query=""
        ))
        elapsed = time.time() - start
        self.assertNotIn("error", result)
        self.assertLess(elapsed, 2.0, f"Took {elapsed:.2f}s, expected <2s")

    def test_empty_result(self):
        """Type with no matches returns empty list, not error."""
        result = asyncio.run(search_symbols(
            project_root=self.project_root, query="", type="import"
        ))
        self.assertNotIn("error", result)
        self.assertEqual(result["symbols"], [])


if __name__ == '__main__':
    unittest.main()
