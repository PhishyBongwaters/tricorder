"""Transcript-item 1 red test: symbols listing render diet.

From r05A1/r06A1 trails: every symbols hit ships ~10 keys, most dead
weight (`signature:""`, `docstring:""`, `body:""`, `callers":null`,
`callees":null`, `stop_note":""`), and multi-line signatures keep
their newlines. Listing output (search_symbols) must drop empty keys
and fold signatures to one line. Detail path (get_symbol_details)
keeps full records — untouched.
"""
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import Tricorder


def _project():
    tmp = Path(tempfile.mkdtemp(prefix="t5diet_"))
    (tmp / "pkg").mkdir()
    (tmp / "pkg" / "mod.py").write_text(
        "def multi_line(a,\n"
        "             b,\n"
        "             c=None):\n"
        "    return (a, b, c)\n"
        "\n"
        "\n"
        "class Plain:\n"
        "    def method(self):\n"
        "        return 1\n",
        encoding="utf-8",
    )
    return tmp


class TestSymbolsDiet(unittest.TestCase):
    def setUp(self):
        self.tmp = _project()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.tc = Tricorder(root=str(self.tmp), use_db=False,
                            verbose=False)

    def test_no_empty_values_in_listing(self):
        results, _ = self.tc.search_symbols("", limit=50)
        self.assertTrue(results)
        for r in results:
            for k, v in r.items():
                self.assertNotIn(v, ("", None, []),
                                 f"dead key {k!r} on {r.get('name')}")

    def test_signature_folded_single_line(self):
        results, _ = self.tc.search_symbols("multi_line", limit=5)
        self.assertTrue(results)
        for r in results:
            if "signature" in r:
                self.assertNotIn("\n", r["signature"])

    def test_structural_keys_always_present(self):
        results, _ = self.tc.search_symbols("", limit=50)
        for r in results:
            for k in ("name", "type", "file", "line", "end_line",
                      "language", "kind"):
                self.assertIn(k, r)


if __name__ == "__main__":
    unittest.main()
