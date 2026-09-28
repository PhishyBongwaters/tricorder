"""Transcript-item 4 red test: MAP hygiene (dedup + rank rounding).

From the r06A1 trail: the rung-1 MAP prints `Error::fmt` line 111
TWICE byte-identical (855 exact-duplicate tag rows in the VW DB), and
ranks print at 17 significant digits (`0.11733934746401727`). Render
hygiene: dedupe ranked tags on (rel,line,name,kind) keeping the first
(highest-ranked); round emitted JSON ranks to 4dp via the shared
`emit_rank` helper (the text path already prints :.4f). Sort stays
full-precision. NOTE: DB-level dup rows (855, extractor double-emit
suspected) are a separate write-path finding, reported, not fixed here.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ranking import _dedupe_ranked_tags
from tricorder import emit_rank
from utils import Tag


def _tag(name, line):
    return Tag(rel_fname="src/error.rs", fname="/r/src/error.rs",
               line=line, name=name, kind="def")


class TestMapHygiene(unittest.TestCase):
    def test_duplicate_rows_deduped_rank_order_kept(self):
        ranked = [(0.11733934746401727, _tag("Error::fmt", 111)),
                  (0.11733934746401727, _tag("Error::fmt", 111)),
                  (0.05, _tag("Empty", 64))]
        out = _dedupe_ranked_tags(ranked)
        self.assertEqual([(t.name, t.line) for _, t in out],
                         [("Error::fmt", 111), ("Empty", 64)])

    def test_ranks_rounded_to_4dp(self):
        self.assertEqual(emit_rank(0.11733934746401727), 0.1173)
        self.assertEqual(emit_rank(1.0), 1.0)


if __name__ == "__main__":
    unittest.main()
