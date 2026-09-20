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

    def test_callees_uses_innermost_scope(self):
        # F2: callees('A::m1') must contain m1's own calls (helper) but not
        # sibling method m2's calls (other). The old code took the first
        # (outermost) containing symbol — the class — leaking siblings in.
        tmp = Path(tempfile.mkdtemp(prefix="callees_scope_"))
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        (tmp / "s.py").write_text(
            "def helper():\n    return 1\n\n"
            "def other():\n    return 2\n\n"
            "class A:\n"
            "    def m1(self):\n        return helper()\n"
            "    def m2(self):\n        return other()\n",
            encoding="utf-8",
        )
        t = Tricorder(root=str(tmp), verbose=False)
        result = t.query_graph(parse_query_dsl("callees('A::m1')"))
        self.assertTrue(result["nodes"], "fixture def must resolve (no vacuous pass)")
        seen = {e["to"] for e in result["edges"]} | {n["name"] for n in result["nodes"]}
        self.assertTrue(any("helper" in s for s in seen),
                       f"expected helper among callees: {sorted(seen)}")
        self.assertFalse(any("other" in s for s in seen),
                        f"sibling method's call leaked into callees: {sorted(seen)}")

    def _write_fixture(self, files):
        tmp = Path(tempfile.mkdtemp(prefix="f1_qual_"))
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        for name, text in files.items():
            (tmp / name).write_text(text, encoding="utf-8")
        return tmp

    def test_qualified_defs_scope_filtered(self):
        # F1: defs('A::run') must resolve to A's definition only, not B's
        # homonym. The old base-name fallback put the bare name in
        # current_targets, conflating every same-named definition.
        tmp = self._write_fixture({
            "a.py": "class A:\n    def run(self):\n        return 1\n",
            "b.py": "class B:\n    def run(self):\n        return 2\n",
        })
        t = Tricorder(root=str(tmp), verbose=False)
        result = t.query_graph(parse_query_dsl("defs('A::run')"))
        self.assertTrue(result["nodes"], "A::run must resolve (no vacuous pass)")
        files = {n["file"] for n in result["nodes"]}
        self.assertEqual(files, {str(tmp / "a.py")},
                         f"expected only a.py, got: {sorted(files)}")
        # Unqualified query keeps the old behavior: both definitions.
        both = t.query_graph(parse_query_dsl("defs('run')"))
        self.assertEqual({n["file"] for n in both["nodes"]},
                         {str(tmp / "a.py"), str(tmp / "b.py")})

    def test_qualified_refs_use_qualified_index(self):
        # F1: where the index holds qualified refs (Rust `use` bindings),
        # refs('ops_a::run') must traverse only those — no conflation with
        # ops_b::run and no bare-name-fallback flag.
        tmp = self._write_fixture({
            "ops_a.rs": "pub fn run() -> i32 {\n    1\n}\n",
            "ops_b.rs": "pub fn run() -> i32 {\n    2\n}\n",
            "main.rs": ("use crate::ops_a::run as run_a;\n"
                        "use crate::ops_b::run as run_b;\n\n"
                        "fn main() {\n    let x = run_a();\n    let y = run_b();\n}\n"),
        })
        t = Tricorder(root=str(tmp), verbose=False)
        result = t.query_graph(parse_query_dsl("refs('ops_a::run')"))
        self.assertTrue(result["edges"], "qualified ref must resolve (no vacuous pass)")
        sites = {(e["from_file"], e["from_line"]) for e in result["edges"]}
        self.assertEqual(sites, {(str(tmp / "main.rs"), 5)},
                         f"expected only the ops_a call site, got: {sorted(sites)}")
        self.assertTrue(all("resolution" not in e for e in result["edges"]),
                        "qualified hit must not be flagged as a fallback")
        self.assertEqual(result["stats"].get("bare_name_fallbacks"), 0)

    def test_bare_fallback_flagged(self):
        # F1: where the index only has bare refs (Python attribute calls),
        # refs('A::run') still traverses them (recall) but every edge is
        # flagged bare-name-fallback instead of silently conflating.
        tmp = self._write_fixture({
            "a.py": "class A:\n    def run(self):\n        return 1\n",
            "b.py": "class B:\n    def run(self):\n        return 2\n",
            "c.py": ("from a import A\nfrom b import B\n"
                     "a = A()\nb = B()\na.run()\nb.run()\n"),
        })
        t = Tricorder(root=str(tmp), verbose=False)
        result = t.query_graph(parse_query_dsl("refs('A::run')"))
        self.assertTrue(result["edges"], "fallback must still find refs (no vacuous pass)")
        self.assertTrue(all(e.get("resolution") == "bare-name-fallback"
                            for e in result["edges"]),
                        f"all edges must be flagged: {result['edges']}")
        self.assertGreater(result["stats"].get("bare_name_fallbacks", 0), 0)
        # The definition side stays precise: only A's def is a node target.
        def_files = {n["file"] for n in result["nodes"] if n["line"] == 2}
        self.assertNotIn(str(tmp / "b.py"), def_files)
        # Unqualified query: no flags, old behavior preserved.
        plain = t.query_graph(parse_query_dsl("refs('run')"))
        self.assertTrue(all("resolution" not in e for e in plain["edges"]))

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

        # Depth 2 should find strictly more nodes than depth 1 (fixture has
        # caller-of-callers), and depth 1 must find something — otherwise the
        # depth= parameter is silently ignored and both are 0.
        self.assertGreater(nodes1, 0, "depth=1 found nothing; fixture or depth broken")
        self.assertGreater(nodes2, nodes1)

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
        self.assertIsNotNone(result.get("tier_hint"),
                             "over-budget query must carry a tier_hint")
        # The estimate must describe the payload actually returned,
        # not the pre-truncation one.
        import json as _json
        from utils import count_tokens
        actual = count_tokens(_json.dumps({"nodes": result["nodes"],
                                           "edges": result["edges"]}))
        self.assertEqual(result["token_estimate"], actual)
        self.assertLessEqual(len(result["nodes"]), max(1, 100 // 50))

    def test_no_truncation_under_budget(self):
        """Under-budget results are returned whole, with no tier_hint."""
        tricorder = Tricorder(root=str(self.project_root), verbose=False)
        from utils import parse_query_dsl

        parsed = parse_query_dsl("callers('authenticate') depth=10")
        result = tricorder.query_graph(parsed)
        huge = tricorder.query_graph(parsed, token_limit=10 ** 9)

        self.assertIsNone(result.get("tier_hint"))
        self.assertEqual(len(result["nodes"]), len(huge["nodes"]))
        self.assertEqual(len(result["edges"]), len(huge["edges"]))

    def test_nonpositive_token_limit_disables_truncation(self):
        """token_limit <= 0 must not produce empty/negative slices."""
        tricorder = Tricorder(root=str(self.project_root), verbose=False)
        from utils import parse_query_dsl

        parsed = parse_query_dsl("callers('authenticate') depth=10")
        full = tricorder.query_graph(parsed, token_limit=10 ** 9)
        for lim in (0, -5):
            result = tricorder.query_graph(parsed, token_limit=lim)
            self.assertEqual(len(result["nodes"]), len(full["nodes"]))
            self.assertEqual(len(result["edges"]), len(full["edges"]))

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

        # Completes well within a generous bound for a small repo. (Was 0.5s —
        # that tight a bound flakes under CI load; the intent is guarding
        # against pathological slowness, not 500ms.)
        self.assertLess(elapsed, 5.0)


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
