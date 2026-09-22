"""Budgeted detect/symbols responses (max_tokens).

Red-first for the detect payload budget (see
docs/PROPOSAL_detect_payload_budget.md): one fuzzy NL query returned
58,624 tokens in a single response. Trim order mirrors detail — drop
per-hit context first (identity survives), then lowest-ranked hits —
reporting truncated/total/omitted. Unbudgeted (max_tokens=None) behavior
is unchanged.
"""
import asyncio
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tricorder_server import tricorder_detect, tricorder_symbols
from utils import count_tokens, enforce_search_budget


def _tok(obj) -> int:
    return count_tokens(json.dumps(obj), "gpt-4")


LONG = "# " + "x" * 3000 + "\n"


class TestEnforceSearchBudget(unittest.TestCase):
    def _items(self, n=4):
        return [
            {"file": f"m{i}.py", "line": 10 + i, "name": f"target_{i}()",
             "kind": "def", "quality": "exact",
             "context": f"m{i}.py\n  10: def target_{i}():\n{LONG}"}
            for i in range(n)
        ]

    def test_none_is_unbounded(self):
        items = self._items()
        out, truncated, omitted = enforce_search_budget(items, None)
        self.assertEqual(out, items)
        self.assertFalse(truncated)
        self.assertEqual(omitted, 0)

    def test_strips_context_before_dropping_hits(self):
        items = self._items()
        # Budget fits all four identities but not their contexts.
        budget = sum(_tok([{k: h[k] for k in ("file", "line", "name")}])
                     for h in items) + 100
        out, truncated, omitted = enforce_search_budget(items, budget)
        self.assertTrue(truncated)
        self.assertEqual(len(out), 4, "contexts go first, hits survive")
        self.assertTrue(all(h["context"] == "" for h in out))
        self.assertLessEqual(_tok(out), budget)

    def test_drops_tail_hits_and_reports(self):
        items = self._items()
        out, truncated, omitted = enforce_search_budget(items, 100)
        self.assertTrue(truncated)
        self.assertGreater(omitted, 0)
        self.assertEqual(omitted, len(items) - len(out))
        self.assertLessEqual(_tok(out), 100)
        # Head identity always survives, even under the floor.
        self.assertEqual(out[0]["file"], "m0.py")
        self.assertEqual(out[0]["name"], "target_0()")
        self.assertIn("line", out[0])

    def test_tiny_budget_keeps_one_identity(self):
        items = self._items()
        out, truncated, omitted = enforce_search_budget(items, 5)
        self.assertTrue(truncated)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["file"], "m0.py")


class TestDetectMaxTokensIntegration(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="detect_budget_"))
        for i in range(4):
            (self.tmp / f"m{i}.py").write_text(
                f"def target_{i}():\n{LONG}    return {i}\n",
                encoding="utf-8", newline="\n")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def test_unbudgeted_unchanged(self):
        r = asyncio.run(tricorder_detect(
            project_root=str(self.tmp), query="target_"))
        self.assertNotIn("error", r)
        self.assertNotIn("truncated", r)
        self.assertEqual(len(r["results"]), 4)

    def test_budget_honored_with_identity(self):
        r = asyncio.run(tricorder_detect(
            project_root=str(self.tmp), query="target_", max_tokens=100))
        self.assertNotIn("error", r)
        self.assertTrue(r.get("truncated"))
        self.assertLessEqual(_tok(r["results"]), 100)
        head = r["results"][0]
        self.assertEqual(head["file"], "m0.py")
        self.assertIn("target_0", head["name"])
        self.assertIn("line", head)
        self.assertGreater(r.get("omitted", 0), 0)

    def test_symbols_budget_honored(self):
        # Symbols carry absolute file paths, so one identity hit alone is
        # ~100 tokens under a workspace-redirected tmp root: budget for two.
        r = asyncio.run(tricorder_symbols(
            project_root=str(self.tmp), query="target_", max_tokens=250))
        self.assertNotIn("error", r)
        self.assertTrue(r.get("truncated"))
        self.assertLessEqual(_tok(r["symbols"]), 250)
        self.assertEqual(r["symbols"][0]["name"], "target_0")


class TestDetectMaxTokensCli(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="detect_cli_budget_"))
        for i in range(4):
            (self.tmp / f"m{i}.py").write_text(
                f"def target_{i}():\n{LONG}    return {i}\n",
                encoding="utf-8", newline="\n")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.cli = str(Path(__file__).resolve().parent.parent / "tricorder.py")

    def _cli(self, *args):
        import subprocess as _sp
        return _sp.run([sys.executable, self.cli, "--root", str(self.tmp),
                        *args], capture_output=True, text=True, timeout=180)

    def test_cli_detect_max_tokens(self):
        r = self._cli("--detect", "target_", "--format", "json",
                      "--max-tokens", "100")
        self.assertEqual(r.returncode, 0, r.stderr[-1000:])
        payload = json.loads(r.stdout)
        self.assertTrue(payload.get("truncated"))
        self.assertLessEqual(_tok(payload["results"]), 100)
        self.assertEqual(payload["results"][0]["file"], "m0.py")


if __name__ == "__main__":
    unittest.main()
