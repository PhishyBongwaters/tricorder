"""Tests for tricorder_query MCP tool (M0.10)."""

import os
import tempfile
import shutil
from pathlib import Path
import unittest

# Ensure we import from the local tricorder package
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from utils import parse_query_dsl, ParsedQuery, TraversalStep, QueryModifiers
from core import Tricorder
from tricorder_server import _budget_fields
from utils import count_tokens

# Test fixture directory
FIXTURE_DIR = Path(__file__).parent / "fixtures" / "graph_query_test"


class TestQueryDSLParser(unittest.TestCase):
    """Test the DSL parser for graph queries."""

    def test_basic_callers(self):
        """Basic callers traversal."""
        parsed = parse_query_dsl("callers('authenticate') depth=2")
        self.assertEqual(len(parsed.steps), 1)
        step = parsed.steps[0]
        self.assertEqual(step.kind, "callers")
        self.assertEqual(step.target, "authenticate")
        self.assertEqual(step.modifiers.depth, 2)

    def test_basic_callees(self):
        """Basic callees traversal."""
        parsed = parse_query_dsl("callees('main')")
        self.assertEqual(len(parsed.steps), 1)
        step = parsed.steps[0]
        self.assertEqual(step.kind, "callees")
        self.assertEqual(step.target, "main")
        self.assertEqual(step.modifiers.depth, 1)  # default

    def test_exclude_glob(self):
        """Exclude glob modifier."""
        parsed = parse_query_dsl("callees('Config') exclude=tests/**")
        step = parsed.steps[0]
        self.assertIn("tests/**", step.modifiers.exclude_globs)

    def test_include_glob(self):
        """Include glob modifier."""
        parsed = parse_query_dsl("refs('Config') include=src/**")
        step = parsed.steps[0]
        self.assertIn("src/**", step.modifiers.include_globs)

    def test_type_filter(self):
        """Type filter modifier."""
        parsed = parse_query_dsl("refs('User') type=class")
        step = parsed.steps[0]
        self.assertEqual(step.modifiers.symbol_type, "class")

    def test_limit(self):
        """Limit modifier."""
        parsed = parse_query_dsl("callers('foo') limit=50")
        step = parsed.steps[0]
        self.assertEqual(step.modifiers.limit, 50)

    def test_chained_traversals(self):
        """Chained traversals with pipe."""
        parsed = parse_query_dsl("callers('foo') | callees('bar') depth=3")
        self.assertEqual(len(parsed.steps), 2)
        self.assertEqual(parsed.steps[0].kind, "callers")
        self.assertEqual(parsed.steps[0].target, "foo")
        self.assertEqual(parsed.steps[1].kind, "callees")
        self.assertEqual(parsed.steps[1].target, "bar")
        self.assertEqual(parsed.steps[1].modifiers.depth, 3)

    def test_double_quotes(self):
        """Double-quoted target."""
        parsed = parse_query_dsl('callers("authenticate") depth=2')
        self.assertEqual(parsed.steps[0].target, "authenticate")

    def test_multiple_exclude(self):
        """Multiple exclude globs."""
        parsed = parse_query_dsl("callers('x') exclude=tests/**,vendor/**")
        step = parsed.steps[0]
        self.assertIn("tests/**", step.modifiers.exclude_globs)
        self.assertIn("vendor/**", step.modifiers.exclude_globs)

    def test_all_kinds(self):
        """All traversal kinds."""
        for kind in ["callers", "callees", "refs", "defs"]:
            parsed = parse_query_dsl(f"{kind}('target')")
            self.assertEqual(parsed.steps[0].kind, kind)

    def test_empty_query_error(self):
        """Empty query raises error."""
        with self.assertRaises(ValueError):
            parse_query_dsl("")

    def test_invalid_syntax_error(self):
        """Invalid syntax raises error."""
        with self.assertRaises(ValueError):
            parse_query_dsl("invalid syntax")


class TestGraphQueryIntegration(unittest.TestCase):
    """Integration tests for query_graph using a test fixture."""

    def setUp(self):
        """Use the pre-created test fixture."""
        self.project_root = FIXTURE_DIR

    def test_basic_callers(self):
        """Test basic callers traversal."""
        tricorder = Tricorder(root=str(self.project_root), verbose=False)
        from utils import parse_query_dsl
        parsed = parse_query_dsl("callers('authenticate') depth=2")
        result = tricorder.query_graph(parsed)

        self.assertIn("nodes", result)
        self.assertIn("edges", result)
        self.assertIn("token_estimate", result)
        self.assertIn("full_repo_estimate", result)
        self.assertIn("savings_pct", result)
        self.assertIn("stats", result)

        # Should find authenticate in main.py and auth.py
        node_names = [(n["name"], n["file"]) for n in result["nodes"]]
        self.assertTrue(any("authenticate" in name for name, _ in node_names))

    def test_exclude_glob_filter(self):
        """Test exclude glob filtering.

        Transportable: globs match project-root-relative paths, so the test
        asserts on relative paths (the old version asserted on the absolute
        path, which spuriously contains 'tests/' from the repo layout and
        passed vacuously on Windows where separators are backslashes).
        """
        tricorder = Tricorder(root=str(self.project_root), verbose=False)
        from utils import parse_query_dsl
        # Baseline: without exclude, auth.py contributes nodes.
        parsed_all = parse_query_dsl("callers('authenticate') depth=2")
        result_all = tricorder.query_graph(parsed_all)
        files_all = {Path(n["file"]).name for n in result_all["nodes"]}
        self.assertIn("auth.py", files_all,
                      "fixture should yield auth.py nodes without exclude")
        # With exclude, no node may come from auth.py.
        parsed = parse_query_dsl("callers('authenticate') depth=2 exclude=auth.py")
        result = tricorder.query_graph(parsed)
        self.assertTrue(result["nodes"], "excluding auth.py should still leave main.py nodes")
        for node in result["nodes"]:
            rel = os.path.relpath(node["file"], str(self.project_root))
            self.assertNotEqual(rel.replace(os.sep, "/"), "auth.py",
                                f"excluded file leaked into results: {node['file']}")

    def test_depth_limiting(self):
        """Test depth limiting."""
        tricorder = Tricorder(root=str(self.project_root), verbose=False)
        from utils import parse_query_dsl

        # Depth 1 should only find direct callers
        parsed1 = parse_query_dsl("callers('validate_credentials') depth=1")
        result1 = tricorder.query_graph(parsed1)
        nodes1 = len(result1["nodes"])

        # Depth 2 should find callers of callers
        parsed2 = parse_query_dsl("callers('validate_credentials') depth=2")
        result2 = tricorder.query_graph(parsed2)
        nodes2 = len(result2["nodes"])

        # Depth 2 should find at least as many (or more) nodes
        self.assertGreaterEqual(nodes2, nodes1)

    def test_type_filter(self):
        """Test type filter."""
        tricorder = Tricorder(root=str(self.project_root), verbose=False)
        from utils import parse_query_dsl
        parsed = parse_query_dsl("refs('Config') type=class")
        result = tricorder.query_graph(parsed)

        # All nodes should be class type
        for node in result["nodes"]:
            self.assertEqual(node["type"], "class")

    def test_token_budget_truncation(self):
        """Test token budget truncation with tier_hint."""
        tricorder = Tricorder(root=str(self.project_root), verbose=False)
        from utils import parse_query_dsl

        # Very small token limit should trigger truncation
        parsed = parse_query_dsl("callers('authenticate') depth=10")
        result = tricorder.query_graph(parsed, token_limit=100)

        self.assertIn("token_estimate", result)
        if result["token_estimate"] > 100:
            self.assertIsNotNone(result.get("tier_hint"))

    def test_not_found(self):
        """Test unknown symbol returns empty result with symbol_not_found flag."""
        tricorder = Tricorder(root=str(self.project_root), verbose=False)
        from utils import parse_query_dsl
        parsed = parse_query_dsl("callers('nonexistent_function_xyz')")
        result = tricorder.query_graph(parsed)

        # Should return empty nodes/edges without error
        self.assertEqual(result["nodes"], [])
        self.assertEqual(result["edges"], [])
        # And explicitly flag that the symbol was not found (not "no callers")
        self.assertTrue(result["symbol_not_found"])

    def test_found_clears_flag(self):
        """Test symbol_not_found is False when symbol exists."""
        tricorder = Tricorder(root=str(self.project_root), verbose=False)
        from utils import parse_query_dsl
        parsed = parse_query_dsl("callers('authenticate')")
        result = tricorder.query_graph(parsed)

        self.assertFalse(result["symbol_not_found"])

    def test_cross_file_edges(self):
        """Test cross-file edges are marked correctly."""
        tricorder = Tricorder(root=str(self.project_root), verbose=False)
        from utils import parse_query_dsl
        parsed = parse_query_dsl("callers('authenticate') depth=2")
        result = tricorder.query_graph(parsed)

        # Should have edges with cross-file references
        cross_file_edges = [e for e in result["edges"] if e.get("from_file") != e.get("to_file")]
        self.assertGreater(len(cross_file_edges), 0)

        # Edge should have from_file and to_file
        for edge in result["edges"]:
            self.assertIn("from_file", edge)
            self.assertIn("to_file", edge)
            self.assertIn("type", edge)

    def test_chained_traversal(self):
        """Test chained traversal."""
        tricorder = Tricorder(root=str(self.project_root), verbose=False)
        from utils import parse_query_dsl
        parsed = parse_query_dsl("callers('authenticate') | callees('validate_credentials') depth=1")
        result = tricorder.query_graph(parsed)

        self.assertIn("nodes", result)
        self.assertIn("edges", result)

    def test_performance(self):
        """Test query performance on small repo."""
        tricorder = Tricorder(root=str(self.project_root), verbose=False)
        from utils import parse_query_dsl
        parsed = parse_query_dsl("callers('authenticate') depth=2")

        import time
        start = time.time()
        result = tricorder.query_graph(parsed)
        elapsed = time.time() - start

        # Should complete in under 500ms for small repo
        self.assertLess(elapsed, 0.5)


class TestGraphQueryMCPTool(unittest.TestCase):
    """Test the MCP tool endpoint (async)."""

    def setUp(self):
        self.project_root = FIXTURE_DIR

    def test_mcp_tool_exists(self):
        """Test that tricorder_query is registered as MCP tool."""
        # This is a basic import test - actual async testing requires MCP client
        from tricorder_server import tricorder_query
        self.assertTrue(callable(tricorder_query))

    def test_mcp_tool_invalid_query(self):
        """Test MCP tool returns error for invalid query."""
        import asyncio
        from tricorder_server import tricorder_query

        async def run():
            result = await tricorder_query(str(self.project_root), "invalid query")
            self.assertIn("error", result)
            self.assertIn("Invalid query syntax", result["error"])

        asyncio.run(run())

    def test_mcp_tool_nonexistent_project(self):
        """Test MCP tool returns error for nonexistent project."""
        import asyncio
        from tricorder_server import tricorder_query

        async def run():
            result = await tricorder_query("/nonexistent/path", "callers('foo')")
            self.assertIn("error", result)
            self.assertIn("not found", result["error"].lower())

        asyncio.run(run())


class TestTestsForTraversal(unittest.TestCase):
    """tests_for('symbol') returns only callers located in test files."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="tests_for_"))
        (self.tmp / "src").mkdir()
        (self.tmp / "tests").mkdir()
        (self.tmp / "src" / "auth.py").write_text(
            "def authenticate(user, password):\n    return user == 'admin'\n",
            encoding="utf-8",
        )
        (self.tmp / "src" / "main.py").write_text(
            "from auth import authenticate\n\ndef run():\n    authenticate('admin', 'x')\n",
            encoding="utf-8",
        )
        (self.tmp / "tests" / "test_auth.py").write_text(
            "from src.auth import authenticate\n\n"
            "def test_login():\n    assert authenticate('admin', 'x')\n\n"
            "def test_bad():\n    assert not authenticate('bob', 'y')\n",
            encoding="utf-8",
        )
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def test_dsl_parses_tests_for(self):
        parsed = parse_query_dsl("tests_for('authenticate')")
        self.assertEqual(len(parsed.steps), 1)
        self.assertEqual(parsed.steps[0].kind, "tests_for")
        self.assertEqual(parsed.steps[0].target, "authenticate")

    def test_is_test_file(self):
        from utils import is_test_file
        for p in ("tests/test_auth.py", "src/tests/test_a.py", "x_test.go",
                  "foo.test.js", "__tests__/a.js", "a_spec.rb", "test_x.py"):
            self.assertTrue(is_test_file(p), p)
        for p in ("src/auth.py", "testing.py", "latest.py", "contest.py"):
            self.assertFalse(is_test_file(p), p)

    def test_only_test_callers_returned(self):
        tricorder = Tricorder(root=str(self.tmp), verbose=False)
        result = tricorder.query_graph(parse_query_dsl("tests_for('authenticate')"))
        self.assertNotIn("error", result)
        node_names = {n["name"] for n in result["nodes"]}
        self.assertIn("test_login", node_names)
        self.assertIn("test_bad", node_names)
        # Non-test caller must be excluded even though it calls authenticate.
        self.assertNotIn("run", node_names)
        for node in result["nodes"]:
            if node["name"] == "authenticate":
                continue
            self.assertIn("tests", node["file"].replace("\\", "/"),
                          f"non-test file leaked: {node['file']}")
        for edge in result["edges"]:
            self.assertEqual(edge["type"], "tests")

    def test_no_tests_found(self):
        tricorder = Tricorder(root=str(self.tmp), verbose=False)
        result = tricorder.query_graph(parse_query_dsl("tests_for('run')"))
        self.assertNotIn("error", result)
        # 'run' is only called from non-test code (nothing calls it here at
        # all) — no test callers expected.
        callers = [n for n in result["nodes"] if n["name"] != "run"]
        self.assertEqual(callers, [])


if __name__ == "__main__":
    unittest.main()
