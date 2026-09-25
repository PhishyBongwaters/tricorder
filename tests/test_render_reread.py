"""MAP fit loop must not re-read files per binary-search probe.

2026-09-25 finding (Go MAP timeout analysis): get_ranked_tags_map_uncached
binary-searches the tag budget (~log2(N) probes) and every try_tags probe
re-renders via to_tree, which reads every selected file from disk TWICE
(line-count precompute in render.py + _render_body) with zero caching
(read_text hits disk on every call). At Go scale (~10k files, ~18 probes)
that is hundreds of thousands of file reads per MAP — stacked on the
per-call PageRank, it guarantees the 120s timeout.

Fix contract: one MAP build reads each file's text at most once total
(per-call memo, discarded after — never a cross-call cache, so edits
between calls always re-read).
"""
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import Tricorder
from utils import read_text as _real_read_text, count_tokens

N_FILES = 10
DEFS_PER_FILE = 6


def _project():
    tmp = Path(tempfile.mkdtemp(prefix="render_reread_"))
    for i in range(N_FILES):
        body = "".join(
            f"def sym{i}_{j}():\n    return {j}\n\n" for j in range(DEFS_PER_FILE)
        )
        (tmp / f"m{i}.py").write_text(body, encoding="utf-8")
    return tmp


class TestMapFitReadsBounded(unittest.TestCase):
    def setUp(self):
        self.tmp = _project()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.calls = []

        def counting_reader(path):
            self.calls.append(path)
            return _real_read_text(path)

        self.tc = Tricorder(root=str(self.tmp), use_db=False, verbose=False,
                            file_reader_func=counting_reader)
        self.files = [os.path.join(str(self.tmp), f"m{i}.py")
                      for i in range(N_FILES)]

    def test_fit_loop_reads_each_file_once(self):
        """Total file-text reads for one MAP build stay O(files), not
        O(probes * files). 60 tags -> ~6 probes; unmemoized code reads
        every selected file twice per probe (>100 reads here)."""
        tree, _ = self.tc.get_ranked_tags_map_uncached(
            [], self.files, 2048)
        self.assertTrue(tree)
        self.assertLessEqual(count_tokens(tree), 2048)
        self.assertLessEqual(
            len(self.calls), 2 * N_FILES,
            f"{len(self.calls)} file reads for {N_FILES} files: "
            f"fit loop re-reads per probe")

    def test_memo_does_not_leak_across_calls(self):
        """A second MAP build re-reads (edits between calls are picked up)
        and renders byte-identical output for unchanged files."""
        first, _ = self.tc.get_ranked_tags_map_uncached([], self.files, 2048)
        n_first = len(self.calls)
        self.calls.clear()
        second, _ = self.tc.get_ranked_tags_map_uncached([], self.files, 2048)
        self.assertEqual(first, second)
        # No cross-call cache: the second build reads files again.
        self.assertGreaterEqual(len(self.calls), N_FILES,
                                "second build served a stale cross-call cache")
        self.assertLessEqual(len(self.calls), 2 * N_FILES)
        self.assertGreater(n_first, 0)


if __name__ == "__main__":
    unittest.main()
