"""T2 red test: smart-map identifier-first skip.

SPEC docs/SPEC-smartmap-identifier-first.md:
- NL question containing `has_many` derives candidates (backticked first)
  and skips MAP on the first exact hit; skip bar (quality==exact) unchanged.
- No-skip case falls through to MAP byte-for-byte (MCP: "map" key present).
- Safety (from the SPEC's conservative constraint): NL filler words
  (the/and/what/does/...) and CODE keywords (class/def/...) never become
  candidates; tokens < 3 chars dropped; at most 3 probes.
"""
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, '.')
from utils import smart_map_candidates, smart_map_exact_hit

RAILS_Q = ("How does ActiveRecord implement the `has_many` association "
           "and what methods does it generate?")


class TestT2Candidates(unittest.TestCase):
    def test_backticked_first(self):
        cands = smart_map_candidates(RAILS_Q)
        self.assertTrue(cands, "expected candidates")
        self.assertEqual(cands[0], "has_many")

    def test_filler_and_keywords_excluded(self):
        cands = smart_map_candidates(RAILS_Q)
        lowered = [c.lower() for c in cands]
        for junk in ["how", "does", "the", "and", "what", "it",
                     "class", "def", "s", "to"]:
            self.assertNotIn(junk, lowered, f"{junk} must not be a candidate")

    def test_cap_three(self):
        cands = smart_map_candidates(
            "Explain Alpha Beta Gamma Delta Epsilon Zeta Eta Theta")
        self.assertLessEqual(len(cands), 3)

    def test_dotted_tail_expanded(self):
        cands = smart_map_candidates("Where is Class.method defined?")
        self.assertIn("method", cands)

    def test_scoped_full_and_tail(self):
        cands = smart_map_candidates("Where is Builder::HasMany defined?")
        self.assertIn("Builder::HasMany", cands)
        self.assertIn("HasMany", cands)

    def test_short_tokens_dropped(self):
        # Bare tokens under 3 chars never become probes...
        cands = smart_map_candidates("Is ab ok or is cd ok?")
        self.assertEqual(cands, [])
        # ...but backticked spans keep author-marked signal even when
        # short (the exact-hit bar still guards the skip).
        cands = smart_map_candidates("Is `ab` ok or is `x` ok?")
        self.assertIn("ab", cands)
        self.assertIn("x", cands)


class TestT2ProbeLoop(unittest.TestCase):
    def _search(self, hits):
        calls = []

        def fn(cand, max_results):
            calls.append(cand)
            if cand in hits:
                return ([{"name": cand, "quality": "exact"}], False)
            return ([], False)

        fn.calls = calls
        return fn

    def test_first_exact_hit_wins_and_stops(self):
        fn = self._search({"beta"})
        hits, tried = smart_map_exact_hit(fn, "Alpha `beta` gamma delta")
        self.assertEqual(len(hits), 1)
        self.assertLessEqual(len(fn.calls), 3)
        # stops at first hit: later candidates never probed
        self.assertEqual(fn.calls[-1], "beta")

    def test_no_hit_returns_empty(self):
        fn = self._search(set())
        hits, tried = smart_map_exact_hit(fn, RAILS_Q)
        self.assertEqual(hits, [])
        self.assertTrue(tried)

    def test_fuzzy_never_skips(self):
        def fn(cand, max_results):
            return ([{"name": cand + "_x", "quality": "fuzzy"}], False)

        hits, _ = smart_map_exact_hit(fn, RAILS_Q)
        self.assertEqual(hits, [])


class TestT2CLITextOutput(unittest.TestCase):
    """The non-JSON text branch of the smart-map skip must not crash.

    Skip hits come from search_identifiers (detect family: "kind"), but the
    text printer read s["type"] (a search_symbols field), so ANY
    identifier exact-hit raised KeyError: 'type' and exited 1. Only
    reachable once T2 makes rung 1 exact-hit on an identifier — which is
    exactly what the v1.9 ladder tells agents to pass. JSON mode was
    unaffected (it dumps the dicts as-is).
    """

    def setUp(self):
        import shutil
        import subprocess
        import tempfile
        self.tmp = Path(tempfile.mkdtemp(prefix="t2smartmap_cli_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        Path(self.tmp, "a.py").write_text(
            "def has_many():\n    return 1\n", encoding="utf-8")
        repo = Path(__file__).resolve().parent.parent
        self._run = lambda *a: subprocess.run(
            [sys.executable, str(repo / "tricorder.py"),
             "--root", str(self.tmp), *a],
            capture_output=True, text=True, timeout=120)

    def test_smart_map_exact_hit_text_does_not_crash(self):
        p = self._run("--smart-map", "has_many")
        self.assertEqual(p.returncode, 0,
                         p.stderr[-800:])
        self.assertNotIn("KeyError", p.stderr)
        self.assertIn("has_many", p.stdout)
        # kind is the detect-family field; type is not present on hits
        self.assertIn("[def]", p.stdout)

    def test_smart_map_text_matches_detect_text_shape(self):
        # Same result family as --detect: rung 1 and rung 2 should render
        # identically so an agent comparing them sees no schema surprise.
        smart = self._run("--smart-map", "has_many")
        detect = self._run("--detect", "has_many", "--max-results", "5")
        self.assertEqual(smart.returncode, 0, smart.stderr[-800:])
        self.assertEqual(detect.returncode, 0, detect.stderr[-800:])
        self.assertIn("has_many", smart.stdout)
        self.assertIn("[def]", smart.stdout)
        self.assertIn("[def]", detect.stdout)
        # MAP was skipped (exact hit), so no map framing in the output
        self.assertNotIn("Repository map", smart.stdout)


class TestT2MCPIntegration(unittest.TestCase):
    def setUp(self):
        import tempfile
        self.tmp = tempfile.mkdtemp(prefix="t2smartmap_")
        self.addCleanup(__import__("shutil").rmtree, self.tmp,
                        ignore_errors=True)
        Path(self.tmp, "a.py").write_text(
            "def has_many():\n    return 1\n", encoding="utf-8")

    def test_nl_question_with_backticked_ident_skips_map(self):
        from tricorder_server import tricorder_scan
        import asyncio
        resp = asyncio.run(tricorder_scan(
            project_root=self.tmp, smart_map=RAILS_Q))
        self.assertNotIn("error", resp)
        self.assertIn("results", resp)
        self.assertNotIn("map", resp)
        self.assertTrue(resp.get("smart_map", {}).get("skipped_map"))

    def test_nl_question_without_hit_falls_through(self):
        from tricorder_server import tricorder_scan
        import asyncio
        resp = asyncio.run(tricorder_scan(
            project_root=self.tmp,
            smart_map="How does the zzz_nonexistent_thing work here?"))
        self.assertNotIn("error", resp)
        self.assertIn("map", resp)


if __name__ == "__main__":
    unittest.main()
