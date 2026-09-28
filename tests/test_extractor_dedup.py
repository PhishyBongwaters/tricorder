"""DB-dupe scoping red test: extractor double-emit vs legit repeats.

From the VW canonical DB: 855 exact-duplicate (rel,line,name,kind)
tag groups. Autopsy separates two classes:
(a) TRUE double-emit: one HCL `variable "DB" {` block parses to FOUR
    identical def rows (same node, same column — multi-capture).
(b) LEGIT same-line repeats: chained `.or_else().or_else()` / nested
    `dirname` — distinct occurrences, distinct columns. MUST survive.
Fix: dedupe at emission on (name,line,COLUMN,kind); Tag schema
unchanged (no DB migration), future scans store clean rows. Existing
DB rows persist until a rebuild (deferred by operator order).
"""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import Tricorder


def _parse(tmp, fname, content):
    tc = Tricorder(root=str(tmp), use_db=False, verbose=False)
    p = tmp / fname
    p.write_text(content, encoding="utf-8")
    return tc.get_tags(str(p), fname)


class TestExtractorDedup(unittest.TestCase):
    def setUp(self):
        import shutil
        self.tmp = Path(tempfile.mkdtemp(prefix="tdup_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def test_hcl_variable_single_def(self):
        tags = _parse(
            self.tmp, "t.hcl",
            '// Set which DB\'s (features) to enable\n'
            'variable "DB" {\n  default = null\n}\n')
        defs = [(t.name, t.line) for t in tags
                if t.name == "DB" and t.kind == "def"]
        self.assertEqual(len(defs), 1)

    def test_same_line_repeats_preserved(self):
        tags = _parse(
            self.tmp, "b.rs",
            'fn main() {\n'
            '    let x = a.or_else(b).or_else(c);\n}\n')
        refs = [(t.name, t.line) for t in tags
                if t.name == "or_else" and t.kind == "ref"]
        self.assertEqual(len(refs), 2)


if __name__ == "__main__":
    unittest.main()
