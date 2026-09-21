"""Red tests: natural-language detect must bridge concept -> symbol.

Live-agent pilot (2026-09-21) showed tricorder_detect returning NO matches
for plain-English queries ("enter exit stack context manager dependency
yield") even though the target symbol's docstring/body/call sites contain
every query token. Name-only matching cannot cross that gap; the
content-backed fallback tier must.
"""
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import Tricorder


def _project():
    tmp = Path(tempfile.mkdtemp(prefix="nl_detect_"))
    (tmp / "deps.py").write_text(
        "def _solve_generator(*, dependant, stack, sub_values):\n"
        "    \"\"\"Enter the dependency's context manager onto the exit stack.\"\"\"\n"
        "    cm = make_context_manager(dependant)\n"
        "    return stack.enter_async_context(cm)\n"
        "\n"
        "\n"
        "def solve_dependencies(request, fields):\n"
        "    path_values, path_errors = request_params_to_args(\n"
        "        fields.path_params, request.path_params\n"
        "    )\n"
        "    query_values, query_errors = request_params_to_args(\n"
        "        fields.query_params, request.query_params\n"
        "    )\n"
        "    return path_values\n"
        "\n"
        "\n"
        "def request_params_to_args(fields, received):\n"
        "    values = {}\n"
        "    for f in fields:\n"
        "        values[f] = received.get(f)\n"
        "    return values\n"
        "\n"
        "\n"
        "def make_pool(kind):\n"
        "    ex = threadpoolexecutor(kind)\n"
        "    return ex\n",
        encoding="utf-8",
    )
    return tmp


class TestNaturalLanguageDetect(unittest.TestCase):
    def setUp(self):
        self.tmp = _project()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.tc = Tricorder(root=str(self.tmp), use_db=False, verbose=False)

    def test_nl_query_hits_docstring_and_body(self):
        # Q1 pilot analog: every token lives in the docstring/body,
        # none in the identifier.
        results, rescue = self.tc.search_identifiers(
            "enter exit stack context manager dependency")
        self.assertTrue(results, "NL query must not come back empty")
        self.assertTrue(rescue)
        top = results[0]
        self.assertEqual(top["name"], "_solve_generator")
        self.assertEqual(top["kind"], "def")
        self.assertEqual(top["quality"], "content")

    def test_nl_query_hits_call_site_context(self):
        # Q4 pilot analog: path/query tokens live at the CALL SITES,
        # "arguments" bridges to "args" via the synonym map.
        results, rescue = self.tc.search_identifiers(
            "converts raw path query values into validated arguments")
        self.assertTrue(results, "NL query must not come back empty")
        self.assertTrue(rescue)
        top = results[0]
        self.assertEqual(top["name"], "request_params_to_args")
        self.assertEqual(top["kind"], "def")
        self.assertEqual(top["quality"], "content")

    def test_nl_query_no_match_stays_empty(self):
        results, rescue = self.tc.search_identifiers("quantum flux capacitor")
        self.assertEqual(results, [])
        self.assertFalse(rescue)

    def test_nl_query_matches_unsplittable_compound(self):
        # "threadpoolexecutor" is one lowercase token (no camel/snake
        # split); "executor"/"thread" must still match via substring.
        # Without substring matching only "pool" (name) would hit and the
        # candidate would fall below the coverage fraction.
        results, rescue = self.tc.search_identifiers("executor thread pool")
        self.assertTrue(rescue)
        names = [r["name"] for r in results]
        self.assertIn("make_pool", names)
        self.assertTrue(all(r["quality"] == "content" for r in results))

    def test_exact_name_still_wins_without_content_tier(self):
        results, rescue = self.tc.search_identifiers("request_params_to_args")
        self.assertTrue(results)
        self.assertFalse(rescue)
        self.assertEqual(results[0]["quality"], "exact")

    def test_content_tier_honors_cap(self):
        results, rescue = self.tc.search_identifiers(
            "enter exit stack context manager dependency", max_results=1)
        self.assertTrue(rescue)
        self.assertLessEqual(len(results), 1)


if __name__ == "__main__":
    unittest.main()
