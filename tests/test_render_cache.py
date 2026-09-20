"""render_tree TreeContext path: API drift, staleness, and LOI leakage.

The TreeContext branch of render_tree was dead: it called
``TreeContext.format(lois)``, but the pinned grep-ast==0.9.0 exposes
``format()`` with no arguments, so every render raised TypeError and
fell back to plain line extraction. These tests pin the repaired path:

- scope-annotated output is actually produced (█ LOI markers),
- the per-Tricorder cache is mtime-validated (no stale code after edit),
- LOIs do not leak between renders sharing a cached tree,
- an unchanged file reuses the cached tree (no rebuild).
"""
import os
import shutil
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import Tricorder


class TestRenderTreeContext(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="renderctx_"))
        self.src = self.tmp / "a.py"
        self.src.write_text("def foo():\n    return 1\n", encoding="utf-8")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def _tc(self):
        # context_lines > 0 selects the TreeContext path.
        return Tricorder(root=str(self.tmp), verbose=False, context_lines=2)

    def test_tree_context_path_is_live(self):
        """Output carries TreeContext LOI markers, not the fallback format."""
        tc = self._tc()
        out = tc.render_tree(str(self.src), "a.py", [2])
        self.assertIn("█", out, "TreeContext LOI marker missing — path is dead")
        self.assertIn("return 1", out)
        # Cache holds (mtime, TreeContext) now.
        mtime, tree = tc.tree_context_cache["a.py"]
        self.assertIsNotNone(mtime)

    def test_rerender_after_edit(self):
        """Edited file re-renders with new code (mtime invalidation)."""
        tc = self._tc()
        first = tc.render_tree(str(self.src), "a.py", [2])
        self.assertIn("█", first)
        self.assertIn("return 1", first)

        time.sleep(0.02)
        self.src.write_text("def foo():\n    return 2\n", encoding="utf-8")
        now = time.time() + 5
        os.utime(self.src, (now, now))

        second = tc.render_tree(str(self.src), "a.py", [2])
        self.assertIn("█", second)
        self.assertIn("return 2", second)
        self.assertNotIn("return 1", second)

    def test_lois_do_not_leak_between_renders(self):
        """A cached tree must not union LOIs across renders."""
        self.src.write_text(
            "def alpha():\n    return 'a'\n\n\ndef beta():\n    return 'b'\n",
            encoding="utf-8",
        )
        tc = self._tc()
        tc.render_tree(str(self.src), "a.py", [2])  # LOI inside alpha
        second = tc.render_tree(str(self.src), "a.py", [6])  # LOI inside beta
        self.assertIn("█    return 'b'", second)
        self.assertNotIn("█    return 'a'", second)

    def test_unchanged_file_reuses_cached_tree(self):
        tc = self._tc()
        tc.render_tree(str(self.src), "a.py", [1])
        tree_before = tc.tree_context_cache["a.py"][1]
        tc.render_tree(str(self.src), "a.py", [2])
        self.assertIs(tc.tree_context_cache["a.py"][1], tree_before)


class TestToTreeBodyParity(unittest.TestCase):
    """to_tree streaming and non-streaming must render identical output.

    The non-streaming branch assumed render_tree's first line is a filename
    header (true for the T0 path and the legacy fallback) and discarded
    rendered_lines[0]. But the resurrected T1 path returns
    TreeContext.format() output whose first line is a code line
    (grep-ast==0.9.0 emits no filename header), so one context line was
    silently dropped — while the streaming branch (via _render_body, which
    never did line surgery) kept it.
    """

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="totree_"))
        self.src = self.tmp / "a.py"
        self.src.write_text(
            '"""Module docstring."""\n\n\ndef foo():\n    return 1\n',
            encoding="utf-8",
        )
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def test_streaming_matches_non_streaming(self):
        from io import StringIO
        tc = Tricorder(root=str(self.tmp), verbose=False, context_lines=2)
        tags = tc.get_tags(str(self.src), "a.py")
        ranked = [(1.0, t) for t in tags]
        self.assertTrue(ranked, "expected tags from the fixture file")

        text = tc.to_tree(ranked, set())
        buf = StringIO()
        tc.to_tree(ranked, set(), writer=buf)
        self.assertEqual(text, buf.getvalue())

    def test_first_context_line_not_dropped(self):
        """The opening docstring line must survive the non-streaming path."""
        tc = Tricorder(root=str(self.tmp), verbose=False, context_lines=2)
        tags = tc.get_tags(str(self.src), "a.py")
        ranked = [(1.0, t) for t in tags]
        text = tc.to_tree(ranked, set())
        # TreeContext renders the docstring's first line with a │ marker;
        # the old code discarded it as if it were a filename header.
        self.assertIn('│"""', text)


if __name__ == "__main__":
    unittest.main()
