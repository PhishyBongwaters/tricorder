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

    def test_search_identifiers_negative_cap(self):
        # A negative cap must not turn into a [:-n] slice surprise.
        results, _ = self.tc.search_identifiers("authenticate", max_results=-3)
        self.assertLessEqual(len(results), 1)
        results, _ = self.tc.search_identifiers("authentcate", max_results=-3)
        self.assertLessEqual(len(results), 1)

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
