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
from utils import canonical_token


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


def _ranking_project():
    # RED-TEST scaffold for IDF ranking: several defs share the generic
    # build/path/dictionary vocabulary; only get_openapi_path carries the
    # rare discriminative tokens (tags/summary/responses).
    tmp = Path(tempfile.mkdtemp(prefix="nl_rank_"))
    (tmp / "generic.py").write_text(
        "def build_path(config):\n"
        "    \"\"\"Build a path from the config dictionary.\"\"\"\n"
        "    return config[\"path\"]\n"
        "\n"
        "\n"
        "def build_path_index(routes):\n"
        "    \"\"\"Build a path index dictionary mapping each route path item.\"\"\"\n"
        "    index = {}\n"
        "    for route in routes:\n"
        "        item = build_path(route)\n"
        "        index[route] = item\n"
        "    return index\n"
        "\n"
        "\n"
        "def build_route_map(routes):\n"
        "    \"\"\"Build a route map from the path dictionary.\"\"\"\n"
        "    return {r: build_path(r) for r in routes}\n"
        "\n"
        "\n"
        "def map_path_items(entries):\n"
        "    \"\"\"Map path items to a route dictionary.\"\"\"\n"
        "    return [build_path(e) for e in entries]\n",
        encoding="utf-8",
    )
    (tmp / "target.py").write_text(
        "def get_openapi_path(route):\n"
        "    \"\"\"Tags, summary, responses for a path.\"\"\"\n"
        "    return {\"tags\": route.tags, \"summary\": route.summary,\n"
        "            \"responses\": route.responses}\n",
        encoding="utf-8",
    )
    return tmp


class TestContentRanking(unittest.TestCase):
    def setUp(self):
        self.tmp = _ranking_project()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.tc = Tricorder(root=str(self.tmp), use_db=False, verbose=False)

    def test_canonical_token_folds_inflected_synonyms(self):
        # "builds" must meet the ("create","make","build","new") group or
        # NL queries like "builds the path dictionary" can never match a
        # build*/make* name, even though matching is plural-insensitive.
        self.assertEqual(canonical_token("builds"), "create")
        self.assertEqual(canonical_token("makes"), "create")
        # No group, no change: never invent a mapping.
        self.assertEqual(canonical_token("responses"), "responses")
        self.assertEqual(canonical_token("status"), "status")

    def test_canonical_token_folds_depend_morphology(self):
        # Q1 pilot analog: the query says "dependency", the code says
        # "dependant" (_solve_generator's parameter). Without morphology
        # folding the query token can never meet the code token.
        self.assertEqual(canonical_token("dependency"),
                         canonical_token("dependant"))
        self.assertEqual(canonical_token("dependencies"),
                         canonical_token("dependant"))
        self.assertEqual(canonical_token("dependent"),
                         canonical_token("dependant"))
        self.assertEqual(canonical_token("depend"), "depend")

    def test_canonical_token_folds_dict_abbreviation(self):
        # Q3 pilot analog: the query says "dictionary", the code says
        # "dict". Code abbreviations must meet their NL expansions.
        self.assertEqual(canonical_token("dictionary"), "dict")
        self.assertEqual(canonical_token("dict"), "dict")

    def test_canonical_token_does_not_fold_news_to_new(self):
        # The inflection strip must not fire on words whose trailing "s"
        # is not a plural: "news" is not "new", and folding it into the
        # (create/make/build/new) group would match every builder.
        self.assertEqual(canonical_token("news"), "news")

    def test_coverage_ranking_prefers_most_concepts_covered(self):
        # Ranking is coverage-first: the definition covering the most
        # distinct query concepts wins. get_openapi_path covers 5/6
        # query concepts (path/dict/tags/summary/responses); the generic
        # builders each cover only 3 (build/path/dictionary). The
        # IDF-weighted score only breaks coverage ties.
        results, rescue = self.tc.search_identifiers(
            "builds path dictionary tags summary responses")
        self.assertTrue(rescue)
        self.assertTrue(results, "NL query must not come back empty")
        self.assertEqual(results[0]["name"], "get_openapi_path")
        self.assertEqual(results[0]["quality"], "content")

    def test_idf_breaks_coverage_ties_toward_rare_tokens(self):
        # Same matched-concept count, different composition: "create" is
        # ubiquitous in this corpus, "quetzal" appears once. IDF must
        # rank the candidate matching the rare discriminative token
        # above the one matching only filler.
        tmp = Path(tempfile.mkdtemp(prefix="nl_idf_tie_"))
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        (tmp / "a.py").write_text(
            "def alpha_index(entries):\n"
            "    \"\"\"Build a path index over the entries.\"\"\"\n"
            "    return {e: entries[e] for e in entries}\n"
            "\n"
            "\n"
            "def beta_index(entries):\n"
            "    \"\"\"Quetzal path index over the entries.\"\"\"\n"
            "    return {e: entries[e] for e in entries}\n"
            "\n"
            "\n"
            "def gamma_builder(cfg):\n"
            "    \"\"\"Build the gamma configuration.\"\"\"\n"
            "    return cfg\n"
            "\n"
            "\n"
            "def delta_builder(cfg):\n"
            "    \"\"\"Build the delta configuration.\"\"\"\n"
            "    return cfg\n",
            encoding="utf-8",
        )
        tc = Tricorder(root=str(tmp), use_db=False, verbose=False)
        results, rescue = tc.search_identifiers("build quetzal path index")
        self.assertTrue(rescue)
        self.assertTrue(results, "NL query must not come back empty")
        # Both alpha_index and beta_index cover 3/4 concepts; the rare
        # "quetzal" must break the tie toward beta_index.
        self.assertEqual(results[0]["name"], "beta_index")
        self.assertEqual(results[0]["quality"], "content")


def _callee_project():
    # RED-TEST scaffold for callee-span expansion: the rare token
    # "quetzal" lives only in inner()'s span; outer() calls inner().
    # "alpha" is the alphabetical-tie decoy: without callee evidence it
    # ties outer() on {orchestrates, pipeline} and wins on name order.
    tmp = Path(tempfile.mkdtemp(prefix="nl_callee_"))
    (tmp / "pipeline.py").write_text(
        "def inner():\n"
        "    \"\"\"Handles the quetzal migration records.\"\"\"\n"
        "    return \"quetzal\"\n"
        "\n"
        "\n"
        "def outer():\n"
        "    \"\"\"Orchestrates the pipeline stages.\"\"\"\n"
        "    x = 1\n"
        "    y = 2\n"
        "    inner()\n"
        "    return True\n"
        "\n"
        "\n"
        "def alpha():\n"
        "    \"\"\"Orchestrates the pipeline stages.\"\"\"\n"
        "    return False\n"
        "\n"
        "\n"
        "def unrelated():\n"
        "    \"\"\"Nothing to do with anything.\"\"\"\n"
        "    return None\n",
        encoding="utf-8",
    )
    return tmp


class TestCalleeExpansion(unittest.TestCase):
    def setUp(self):
        self.tmp = _callee_project()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.tc = Tricorder(root=str(self.tmp), use_db=False, verbose=False)

    def test_callee_span_tokens_rank_caller_first(self):
        # Q3 pilot analog: get_openapi_path's discriminative tokens
        # (tags/summary/responses) live in its callee
        # get_openapi_operation, not in its own span. Bounded callee
        # evidence must lift the caller above the alphabetical decoy.
        results, rescue = self.tc.search_identifiers(
            "orchestrates pipeline quetzal")
        self.assertTrue(rescue)
        self.assertTrue(results, "NL query must not come back empty")
        self.assertEqual(results[0]["name"], "outer")
        self.assertEqual(results[0]["quality"], "content")

    def test_callee_only_single_token_query_does_not_surface_caller(self):
        # The absolute score floor must keep working: a one-token query
        # matching only via a callee (0.5x weight) must not surface the
        # caller on its own.
        results, _ = self.tc.search_identifiers("quetzal")
        names = [r["name"] for r in results]
        self.assertNotIn("outer", names)


def _hub_project():
    # RED-TEST scaffold for callee-coverage inflation: the hub calls four
    # helpers whose BODIES collectively cover nearly every query concept,
    # but the hub's OWN evidence (name/span/caller) covers barely a third
    # — the callee names in its body carry no query vocabulary beyond
    # open/api/path. Callee evidence must add score only, never coverage:
    # otherwise the hub wins on borrowed concepts.
    tmp = Path(tempfile.mkdtemp(prefix="nl_hub_"))
    (tmp / "target.py").write_text(
        "def get_openapi_path(route):\n"
        "    \"\"\"Build the path item dict for one route, with params and responses.\"\"\"\n"
        "    meta = fetch_meta(route)\n"
        "    return {\"path\": route.path, \"item\": meta}\n"
        "\n"
        "\n"
        "def fetch_meta(route):\n"
        "    \"\"\"Operation metadata: tags and summary for the OpenAPI operation.\"\"\"\n"
        "    return {\"tags\": route.tags, \"summary\": route.summary}\n",
        encoding="utf-8",
    )
    (tmp / "hub.py").write_text(
        "from target import get_openapi_path, fetch_meta\n"
        "\n"
        "\n"
        "def build_effective_context(routes):\n"
        "    \"\"\"Build everything for all routes.\"\"\"\n"
        "    out = {}\n"
        "    for route in routes:\n"
        "        x1 = get_openapi_path(route)\n"
        "        x2 = fetch_meta(route)\n"
        "        x3 = helper_a(route)\n"
        "        x4 = helper_b(route)\n"
        "    return out\n"
        "\n"
        "\n"
        "def helper_a(route):\n"
        "    \"\"\"Collect params for the OpenAPI item.\"\"\"\n"
        "    return route.params\n"
        "\n"
        "\n"
        "def helper_b(route):\n"
        "    \"\"\"Collect responses per item.\"\"\"\n"
        "    return route.responses\n",
        encoding="utf-8",
    )
    return tmp


class TestCalleeCoverageInflation(unittest.TestCase):
    def setUp(self):
        self.tmp = _hub_project()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.tc = Tricorder(root=str(self.tmp), use_db=False, verbose=False)

    def test_callee_hits_do_not_inflate_coverage(self):
        # FastAPI Q3 analog: the hub's callees' BODIES collectively cover
        # nearly every query concept, but the hub's OWN evidence
        # (name/span/caller) covers barely a third of them. Callee
        # evidence must add score only — never coverage — so the hub
        # cannot even clear the floor on borrowed concepts, let alone
        # outrank the target it merely orchestrates.
        results, rescue = self.tc.search_identifiers(
            "builds the per-route path item dictionary containing tags "
            "summary operationId parameters responses for OpenAPI")
        self.assertTrue(rescue)
        self.assertTrue(results, "NL query must not come back empty")
        names = [r["name"] for r in results]
        self.assertIn("get_openapi_path", names)
        self.assertNotIn("build_effective_context", names,
                         "hub must not clear the coverage floor on "
                         "borrowed callee concepts")
        for r in results:
            self.assertEqual(r["quality"], "content")


if __name__ == "__main__":
    unittest.main()
