"""Symbol names must stay identifiers, never source spans.

2026-09-24 finding (agent leg A-Rails-Q1): `symbols "has_many"` returned a
70,512-char "name" (an entire Ruby module incl. RDoc) — one record, 23k
tokens. Root cause, two parts in parser.get_symbols name resolution:

1. Greedy document-order pairing lets an OUTER nested scope steal an
   INNER scope's name node (both spans contain it); the inner definition
   then falls through to the whole-parent-text fallback. Fix: pair
   innermost-first (stable sort by span).
2. The last-resort fallback (`name = parent.text`) is unbounded. Fix:
   first line, stripped, capped at 200 chars.

Transportable: inline Ruby fixture with the nesting+RDoc shape (no
testbed checkout needed).
"""
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import Tricorder

# Nested modules + interleaved RDoc: outer scopes' spans all contain the
# inner names, which is what broke greedy pairing on Rails form_helper.rb.
FIXTURE = (
    "# big doc\n" * 200
    + "module A\n  module B\n"
    + "# more doc\n" * 200
    + "    module C\n      def c1; end\n    end\n  end\nend\n"
)


class TestSymbolNameSpan(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="symspan_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        (self.tmp / "t.rb").write_text(FIXTURE, encoding="utf-8")
        self.tc = Tricorder(root=str(self.tmp), verbose=False)
        self.files = [str(self.tmp / "t.rb")]

    def test_nested_module_names_exact(self):
        rows, _ = self.tc.search_symbols("", limit=200, files=self.files)
        names = [r["name"] for r in rows]
        for want in ("A", "B", "C", "c1"):
            self.assertIn(want, names)

    def test_no_span_names(self):
        rows, _ = self.tc.search_symbols("", limit=200, files=self.files)
        for r in rows:
            self.assertLessEqual(len(r["name"]), 200, r["name"][:80])
            self.assertNotIn("\n", r["name"])


if __name__ == "__main__":
    unittest.main()
