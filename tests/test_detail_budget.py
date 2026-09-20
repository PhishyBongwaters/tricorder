"""Tests for budget-aware tricorder_detail (max_tokens)."""
import asyncio
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tricorder_server import (
    tricorder_detail,
    _enforce_detail_budget,
    _truncate_text_to_tokens,
    _detail_decoration_reserve,
)
from utils import count_tokens


def _tok(obj) -> int:
    return count_tokens(json.dumps(obj), "gpt-4")


def _symbol(**over):
    d = {
        "name": "big_function",
        "type": "function",
        "file": "/tmp/x/big.py",
        "line": 1,
        "end_line": 300,
        "signature": "big_function ()",
        "docstring": "A very large function.",
        "language": "python",
        "kind": "function_definition",
        "body": "def big_function():\n" + "".join(f"    x{i} = {i}\n" for i in range(60)),
        "callers": [{"file": "other.py", "line": 3 + i, "cross_file": True} for i in range(5)],
        "callees": [{"name": f"compute_{i}", "file": "big.py", "line": 2 + i, "cross_file": False}
                    for i in range(40)],
        "stop_note": "",
    }
    d.update(over)
    return d


class TestTruncateTextToTokens(unittest.TestCase):
    def test_within_budget_unchanged(self):
        t = "hello world"
        self.assertEqual(_truncate_text_to_tokens(t, 100), t)

    def test_truncation_marked_and_head_kept(self):
        t = "\n".join(f"line {i} with some content here" for i in range(50))
        out = _truncate_text_to_tokens(t, 20)
        self.assertLessEqual(count_tokens(out, "gpt-4"), 20 + 12)  # + marker
        self.assertTrue(out.startswith("line 0"))
        self.assertIn("[truncated to fit max_tokens]", out)
        # No mid-line cut: last content line is complete.
        self.assertNotIn("line 49", out)

    def test_zero_budget(self):
        self.assertEqual(_truncate_text_to_tokens("abc", 0), "")


class TestEnforceDetailBudget(unittest.TestCase):
    def test_no_trim_when_fits(self):
        s = _symbol()
        self.assertFalse(_enforce_detail_budget(s, 100_000))
        self.assertEqual(len(s["callees"]), 40)
        self.assertNotIn("[truncated", s["body"])
        # Untrimmed responses stay lean: no count metadata.
        self.assertNotIn("callees_total", s)
        self.assertNotIn("callers_total", s)

    def test_body_truncated_first(self):
        s = _symbol()
        full_body = s["body"]
        # Budget that fits metadata + callers + callees plus a truncated body.
        probe = dict(s, body="")
        budget = _tok(probe) + 200
        self.assertTrue(_enforce_detail_budget(s, budget))
        self.assertLessEqual(_tok(s), budget)
        self.assertLess(len(s["body"]), len(full_body))
        self.assertIn("[truncated to fit max_tokens]", s["body"])
        self.assertTrue(s["body"].startswith("def big_function():"))
        # Callees/callers untouched when body trim suffices — and no
        # count metadata appears for lists that were not shortened.
        self.assertEqual(len(s["callees"]), 40)
        self.assertEqual(len(s["callers"]), 5)
        self.assertNotIn("callees_total", s)
        self.assertNotIn("callers_total", s)

    def test_call_lists_top_n_with_counts(self):
        s = _symbol()
        # Tight budget: both lists must shrink, but neither is dropped
        # silently — each keeps a top-N head with explicit totals, and the
        # higher-priority callers keep at least as good a head.
        floor_no_callees = _tok(dict(s, body="", callees=[], callers=s["callers"][:1]))
        budget = floor_no_callees + 200
        self.assertTrue(_enforce_detail_budget(s, budget))
        self.assertLessEqual(_tok(s), budget)
        self.assertGreater(len(s["callees"]), 0)
        self.assertLess(len(s["callees"]), 40)
        self.assertEqual(s["callees_total"], 40)
        self.assertEqual(s["callees_omitted"], 40 - len(s["callees"]))
        # Head retained: the first (in-file, most local) callee survives.
        self.assertEqual(s["callees"][0]["name"], "compute_0")
        self.assertGreaterEqual(len(s["callers"]), 1)
        self.assertEqual(s["callers"][0]["line"], 3)
        # Signature metadata never cut.
        self.assertEqual(s["signature"], "big_function ()")
        self.assertEqual(s["name"], "big_function")

    def test_callees_take_full_room_when_no_callers(self):
        # With no callers to reserve for, an empty list reserves no room:
        # callees may use the whole list budget instead of a 1/3 share.
        # Also covers the empty-list edge: no orphan count keys appear for
        # a list that started empty.
        s = _symbol(callers=[], body="x = 1\n" * 200)
        floor = _tok(dict(s, body="", callees=[]))
        budget = floor + 150
        self.assertTrue(_enforce_detail_budget(s, budget))
        self.assertLessEqual(_tok(s), budget)
        # Full room (not a 1/3 share) is observable: the capped share keeps
        # a single head at this budget, the full room keeps several.
        self.assertGreaterEqual(len(s["callees"]), 3)
        self.assertLess(len(s["callees"]), 40)
        self.assertEqual(s["callees_total"], 40)
        self.assertEqual(s["callees_omitted"], 40 - len(s["callees"]))
        self.assertEqual(s["callees"][0]["name"], "compute_0")
        self.assertNotIn("callers_total", s)
        self.assertNotIn("callers_omitted", s)
        self.assertEqual(s["callers"], [], "empty list stays empty")

    def test_tiny_budget_best_effort(self):
        s = _symbol()
        # Below the metadata floor: best effort, metadata survives. Lists cut
        # to zero keep their totals — the payload is never silently empty.
        self.assertTrue(_enforce_detail_budget(s, 10))
        self.assertEqual(s["name"], "big_function")
        self.assertEqual(s["signature"], "big_function ()")
        self.assertEqual(s["body"], "")
        self.assertEqual(s["callees"], [])
        self.assertEqual(s["callees_total"], 40)
        self.assertEqual(s["callees_omitted"], 40)
        self.assertEqual(s["callers"], [])
        self.assertEqual(s["callers_total"], 5)
        self.assertEqual(s["callers_omitted"], 5)

    def test_hot_symbol_top_n_with_counts(self):
        # F5 regression: a hot symbol with thousands of callers/callees must
        # keep a useful top-N head plus explicit totals — not empty lists —
        # and the head must be the local (in-file-first) neighborhood.
        n = 2000
        s = _symbol(
            body="",
            callers=[{"file": "other.py", "line": i, "cross_file": True}
                     for i in range(n)],
            callees=[{"name": f"c{i}", "file": "big.py", "line": i,
                      "cross_file": False} for i in range(n)],
        )
        floor = _tok(dict(s, body="", callees=[], callers=[]))
        budget = floor + 1000
        self.assertTrue(_enforce_detail_budget(s, budget))
        self.assertLessEqual(_tok(s), budget)
        for key in ("callees", "callers"):
            kept = s[key]
            self.assertGreater(len(kept), 0, f"{key} should keep a head")
            self.assertLess(len(kept), n, f"{key} should be shortened")
            self.assertEqual(s[f"{key}_total"], n)
            self.assertEqual(s[f"{key}_omitted"], n - len(kept))
        self.assertEqual(s["callees"][0]["name"], "c0")
        self.assertEqual(s["callers"][0]["line"], 0)


class TestDetailMaxTokensIntegration(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="detail_budget_"))
        lines = ["def target_func(a, b):", '    """Add two things."""']
        lines += [f"    step{i} = a + b + {i}" for i in range(80)]
        lines.append("    return step0")
        (self.tmp / "mod.py").write_text("\n".join(lines) + "\n", encoding="utf-8")
        (self.tmp / "use.py").write_text(
            "from mod import target_func\n\ndef caller_one():\n    return target_func(1, 2)\n",
            encoding="utf-8",
        )
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def _detail(self, **kw):
        return asyncio.run(tricorder_detail(
            project_root=str(self.tmp), file="mod.py", name="target_func", **kw))

    def test_no_budget_unchanged(self):
        r = self._detail()
        self.assertNotIn("error", r)
        self.assertNotIn("truncated", r)

    def test_budget_honored(self):
        # Untrimmed response is ~400 tokens; 250 forces trimming.
        r = self._detail(max_tokens=250)
        self.assertNotIn("error", r)
        self.assertTrue(r.get("truncated"))
        self.assertLessEqual(_tok(r), 250)
        sym = r["symbol"]
        self.assertEqual(sym["signature"], "target_func (a, b)")
        self.assertTrue(sym["callers"], "callers should survive budgeting")

    def test_generous_budget_no_truncation(self):
        r = self._detail(max_tokens=100_000)
        self.assertNotIn("truncated", r)

    def test_decoration_reserve_sane(self):
        reserve = _detail_decoration_reserve()
        self.assertGreater(reserve, 0)
        self.assertLess(reserve, 200)


if __name__ == "__main__":
    unittest.main()
