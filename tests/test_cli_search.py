"""Tests for --detect/--symbols CLI flags and the core search methods behind them."""
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import Tricorder

REPO = Path(__file__).resolve().parent
CLI = str(REPO.parent / "tricorder.py")
PY = sys.executable


def _project():
    tmp = Path(tempfile.mkdtemp(prefix="cli_search_"))
    (tmp / "src").mkdir()
    (tmp / "src" / "auth.py").write_text(
        "def authenticate(user, password):\n    return user == 'admin'\n",
        encoding="utf-8",
    )
    (tmp / "src" / "main.py").write_text(
        "from auth import authenticate\n\ndef run():\n    authenticate('admin', 'x')\n",
        encoding="utf-8",
    )
    return tmp


class TestCoreSearch(unittest.TestCase):
    def setUp(self):
        self.tmp = _project()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.tc = Tricorder(root=str(self.tmp), use_db=False, verbose=False)

    def test_search_identifiers(self):
        results, rescue = self.tc.search_identifiers("authenticate")
        self.assertFalse(rescue)
        self.assertTrue(results)
        names = {r["name"] for r in results}
        self.assertIn("authenticate", names)
        kinds = {r["kind"] for r in results}
        self.assertIn("def", kinds)
        self.assertIn("ref", kinds)
        for r in results:
            self.assertEqual(r["quality"], "exact")
            self.assertIn("context", r)

    def test_search_identifiers_exact_mode(self):
        results, _ = self.tc.search_identifiers(
            "authenticate", search_mode="exact")
        # all([]) is True — assert non-empty first or exact-mode silently
        # returning nothing passes.
        self.assertTrue(results)
        self.assertTrue(all(r["name"] == "authenticate" for r in results))

    def test_search_identifiers_bad_regex(self):
        with self.assertRaises(ValueError):
            self.tc.search_identifiers("([invalid", search_mode="regex")

    def test_search_identifiers_rescue(self):
        results, rescue = self.tc.search_identifiers("authentcate")  # typo
        self.assertTrue(rescue)
        self.assertTrue(results)
        self.assertTrue(all(r["quality"] == "fuzzy" for r in results))

    def test_search_identifiers_rescue_honors_cap(self):
        # Rescue over-collects 2x for re-ranking; the caller-facing
        # cap must still hold.
        results, rescue = self.tc.search_identifiers("authentcate", max_results=1)
        self.assertTrue(rescue)
        self.assertLessEqual(len(results), 1)

    def test_search_identifiers_dot_qualified(self):
        # F3: a natural "Model.save" query must resolve the stored
        # "Model::save" tag instead of falling through to fuzzy junk.
        tmp = Path(tempfile.mkdtemp(prefix="dot_qual_"))
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        (tmp / "m.py").write_text(
            "class Model:\n    def save(self):\n        return True\n",
            encoding="utf-8",
        )
        tc = Tricorder(root=str(tmp), use_db=False, verbose=False)
        results, rescue = tc.search_identifiers("Model.save")
        self.assertTrue(results, "dot-qualified query should hit the qualified tag")
        names = [r["name"] for r in results]
        self.assertIn("Model::save", names)
        # The real qualified tag must outrank fuzzy lookalikes.
        self.assertEqual(names[0], "Model::save")

    def test_search_identifiers_finds_argument_position_refs(self):
        # Q2 pilot analog: http_exception_handler is registered as the
        # default handler via
        #   handlers.setdefault(HTTPException, http_exception_handler)
        # a bare identifier in argument position, not a call target.
        # The tagger must emit ref tags for call arguments, or the
        # registration site is invisible to detect/symbols/detail.
        (self.tmp / "src" / "registry.py").write_text(
            "from auth import authenticate\n"
            "\n"
            "handlers = {}\n"
            "handlers.setdefault(ValueError, authenticate)\n",
            encoding="utf-8",
        )
        results, _ = self.tc.search_identifiers("authenticate")
        ref_hits = [r for r in results
                    if r["kind"] == "ref" and "registry.py" in r["file"]]
        self.assertTrue(ref_hits,
                        "call-argument refs must be tagged so registration "
                        "sites are findable")
        self.assertIn(4, [r["line"] for r in ref_hits])

    def test_query_variants_dot_qualified_ranked_first(self):
        from utils import query_variants
        variants = query_variants("Model.save")
        self.assertEqual(variants[0], "Model::save")

    def test_search_identifiers_negative_cap(self):
        # A negative cap must not turn into a [:-n] slice surprise.
        results, _ = self.tc.search_identifiers("authenticate", max_results=-3)
        self.assertLessEqual(len(results), 1)
        results, _ = self.tc.search_identifiers("authentcate", max_results=-3)
        self.assertLessEqual(len(results), 1)

    def test_search_identifiers_empty_query_returns_nothing(self):
        # An empty query substring-matches every identifier; it must not
        # ship arbitrary tags labeled "exact".
        results, rescue = self.tc.search_identifiers("")
        self.assertEqual(results, [])
        self.assertFalse(rescue)

    def test_search_identifiers_cap_has_upper_bound(self):
        # search_identifiers honors the same 200 hard cap as search_symbols —
        # an absurd cap cannot produce an unbounded payload.
        results, _ = self.tc.search_identifiers(
            "authenticate", max_results=999999999)
        self.assertLessEqual(len(results), 200)

    def test_search_identifiers_keeps_match_when_context_empty(self):
        # A tag match must survive even when context rendering yields
        # nothing (e.g. the file became unreadable between tagging and
        # render): the symbol is reported with empty context instead of
        # being silently dropped from the results.
        import unittest.mock as _mock
        with _mock.patch.object(self.tc, "render_tree", return_value=""):
            results, _ = self.tc.search_identifiers("authenticate")
        self.assertTrue(results)
        self.assertIn("authenticate", {r["name"] for r in results})
        self.assertTrue(all(r["context"] == "" for r in results))

    def test_search_identifiers_strips_blank_context_lines(self):
        # Render diet: blank/whitespace-only lines are dropped from the
        # context window. The match line is always kept and survivors
        # keep their numbers, so no positional accuracy is lost.
        tmp = Path(tempfile.mkdtemp(prefix="cli_search_blank_"))
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        (tmp / "spaced.py").write_text(
            "\n\ndef spaced_out():\n\n\n    return 1\n\n",
            encoding="utf-8",
        )
        tc = Tricorder(root=str(tmp), use_db=False, verbose=False)
        results, _ = tc.search_identifiers("spaced_out", context_lines=2)
        self.assertTrue(results)
        hit = next(r for r in results if r["name"] == "spaced_out"
                   and r["kind"] == "def")
        body_lines = hit["context"].splitlines()[1:]  # skip rel_fname header
        # The def line (3) is present with its number intact.
        self.assertTrue(any(l.startswith("  3:") and "def spaced_out" in l
                            for l in body_lines))
        # No blank/whitespace-only rendered lines remain.
        for l in body_lines:
            code = l.split(": ", 1)[1] if ": " in l else ""
            self.assertTrue(code.strip(), f"blank context line kept: {l!r}")

    def test_search_identifiers_default_window_is_one(self):
        # Lean default: ±1 line. The ref hit sits on line 3 with live code
        # on lines 1 and 5: with the old ±2 default those distance-2 lines
        # leaked into the context; with ±1 they must not. Callers needing
        # more pass context_lines explicitly; file/line/name stay exact.
        tmp = Path(tempfile.mkdtemp(prefix="cli_search_window_"))
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        (tmp / "m.py").write_text(
            "x = 1\n"
            "y = 2\n"
            "authenticate('a', 'b')\n"
            "z = 4\n"
            "w = 5\n",
            encoding="utf-8",
        )
        tc = Tricorder(root=str(tmp), use_db=False, verbose=False)
        results, _ = tc.search_identifiers("authenticate")
        hit = next(r for r in results if r["line"] == 3)
        nums = [int(l.strip().split(":")[0])
                for l in hit["context"].splitlines()[1:]]
        self.assertEqual(sorted(nums), [2, 3, 4])
        # And the explicit opt-out still works:
        wide, _ = tc.search_identifiers("authenticate", context_lines=2)
        hit_wide = next(r for r in wide if r["line"] == 3)
        nums_wide = [int(l.strip().split(":")[0])
                     for l in hit_wide["context"].splitlines()[1:]]
        self.assertEqual(sorted(nums_wide), [1, 2, 3, 4, 5])

    def test_search_symbols(self):
        results, rescue = self.tc.search_symbols("auth")
        self.assertFalse(rescue)
        self.assertTrue(any(r["name"] == "authenticate" for r in results))

    def test_search_symbols_type_filter(self):
        results, _ = self.tc.search_symbols("", type="function")
        self.assertTrue(results)
        self.assertTrue(all(r["type"] == "function" for r in results))

    def test_search_symbols_file_filter(self):
        results, _ = self.tc.search_symbols("", file="main.py")
        self.assertTrue(results)
        self.assertTrue(all("main.py" in r["file"] for r in results))

    def test_search_symbols_limit_cap(self):
        results, _ = self.tc.search_symbols("", limit=10_000)
        self.assertLessEqual(len(results), 200)


class TestCliSearch(unittest.TestCase):
    def setUp(self):
        self.tmp = _project()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def _run(self, *args):
        return subprocess.run(
            [PY, CLI, "--root", str(self.tmp), *args],
            capture_output=True, text=True, timeout=120,
        )

    def test_detect_json(self):
        p = self._run("--detect", "authenticate", "--format", "json")
        self.assertEqual(p.returncode, 0, p.stderr[-500:])
        d = json.loads(p.stdout)  # must be pure JSON
        self.assertIn("results", d)
        self.assertTrue(d["results"])
        self.assertTrue(any(r["name"] == "authenticate" and r["kind"] == "def"
                            for r in d["results"]))

    def test_detect_text(self):
        p = self._run("--detect", "authenticate", "--max-results", "2")
        self.assertEqual(p.returncode, 0, p.stderr[-500:])
        self.assertIn("authenticate", p.stdout)
        self.assertIn("[def]", p.stdout)

    def test_detect_no_match_text(self):
        p = self._run("--detect", "zz_no_such_symbol_zz")
        self.assertEqual(p.returncode, 0, p.stderr[-500:])
        self.assertIn("No matches", p.stdout)

    def test_symbols_json(self):
        p = self._run("--symbols", "auth", "--format", "json")
        self.assertEqual(p.returncode, 0, p.stderr[-500:])
        d = json.loads(p.stdout)
        self.assertIn("symbols", d)
        self.assertTrue(any(s["name"] == "authenticate" for s in d["symbols"]))

    def test_symbols_text(self):
        p = self._run("--symbols", "run")
        self.assertEqual(p.returncode, 0, p.stderr[-500:])
        self.assertIn("run", p.stdout)

    def test_map_json_pure(self):
        # Map-mode JSON must be machine-parseable: info chatter
        # ("auto-scanning...") goes nowhere on stdout in JSON mode.
        p = self._run("--format", "json", "--no-db")
        self.assertEqual(p.returncode, 0, p.stderr[-500:])
        d = json.loads(p.stdout)  # raises if stdout is polluted
        self.assertIn("tags", d)
        self.assertNotIn("auto-scanning", p.stdout)

    def test_map_text_keeps_info(self):
        # ...but text mode still shows the human chatter.
        p = self._run("--no-db")
        self.assertEqual(p.returncode, 0, p.stderr[-500:])
        self.assertIn("auto-scanning", p.stdout)


if __name__ == "__main__":
    unittest.main()
