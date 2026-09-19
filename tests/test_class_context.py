"""Structural class-context qualification (Class::method) tests.

Covers the tree-based qualifier shared by the sequential path
(ParserMixin.get_tags_raw) and the parallel path (_parse_worker), plus the
extractor-version staleness gate that invalidates DBs built by older
extractors.
"""
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from parser import ParserMixin, qualify_with_class_context
from ranking import _parse_worker, _apply_class_context_to_rows
from database import DBStore, EXTRACTOR_VERSION

PY_CODE = '''
class Renderer:
    def render(self, x):
        return x

    def helper(self):
        pass

def top_level():
    pass

class Outer:
    class Inner:
        def deep(self):
            pass
'''


class _FakeNode:
    parent = None


class _Harness(ParserMixin):
    def __init__(self, files):
        self.output_handlers = {
            'error': lambda m: None, 'warning': lambda m: None,
            'info': lambda m: None, 'success': lambda m: None,
        }
        self._files = files
        self.read_text_func_internal = lambda fname: self._files.get(fname, "")


class TestStructuralQualification(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile('w', suffix='.py', delete=False)
        self.tmp.write(PY_CODE)
        self.tmp.close()
        self.fname = self.tmp.name
        self.rel = os.path.basename(self.fname)

    def tearDown(self):
        os.unlink(self.fname)

    def test_worker_qualifies_python_methods(self):
        rows = _parse_worker((self.fname, self.rel))
        names = {r[3] for r in rows if r[4] == 'def'}
        self.assertIn('Renderer::render', names)
        self.assertIn('Renderer::helper', names)
        self.assertIn('top_level', names)  # module-level: unqualified
        self.assertIn('Renderer', names)    # class def: never qualified
        self.assertNotIn('render', names)

    def test_nested_class_innermost_wins(self):
        rows = _parse_worker((self.fname, self.rel))
        names = {r[3] for r in rows if r[4] == 'def'}
        self.assertIn('Inner::deep', names)

    def test_no_double_qualification(self):
        # Names already carrying :: pass through untouched.
        self.assertEqual(
            qualify_with_class_context('PCM::AddToBuffer', _FakeNode(),
                                       'name.definition.function'),
            'PCM::AddToBuffer')

    def test_class_defs_never_qualified(self):
        self.assertEqual(
            qualify_with_class_context('Renderer', _FakeNode(),
                                       'name.definition.class'),
            'Renderer')

    def test_sequential_parallel_parity(self):
        rows = _parse_worker((self.fname, self.rel))
        h = _Harness({self.fname: PY_CODE})
        tags = h.get_tags_raw(self.fname, self.rel)
        row_names = sorted((r[2], r[3]) for r in rows if r[4] == 'def')
        tag_names = sorted((t.line, t.name) for t in tags if t.kind == 'def')
        self.assertEqual(row_names, tag_names)

    def test_fallback_heuristic_still_applies(self):
        # Grammars without a mapped class node keep the old paren-based
        # heuristic via _apply_class_context_to_rows.
        rows = [('a.cpp', 'a.cpp', 10, 'PCM', 'def'),
                ('a.cpp', 'a.cpp', 20, 'AddToBuffer(int x)', 'def')]
        out = _apply_class_context_to_rows(rows)
        self.assertEqual(out[1][3], 'PCM::AddToBuffer(int x)')

    def test_mixin_method_legacy_contract(self):
        h = _Harness({})
        # "" (not None) when there is no enclosing class.
        self.assertEqual(h._enclosing_class_name(_FakeNode()), "")


class TestExtractorStalenessGate(unittest.TestCase):
    def test_old_extractor_db_is_rescanned(self):
        from core import Tricorder
        tmpdir = tempfile.mkdtemp()
        src = os.path.join(tmpdir, 'mod.py')
        Path(src).write_text(PY_CODE)
        db_path = os.path.join(tmpdir, 'tags.db')

        tri = Tricorder(root=tmpdir, db_path=db_path)
        tri.get_ranked_tags([src], [])
        db = DBStore(db_path)
        self.assertEqual(db.get_meta()[3], EXTRACTOR_VERSION)

        # Simulate a DB built by the previous extractor: downgrade the stamp
        # but leave tags + file_state untouched (no dirty files). Without the
        # staleness gate the second scan would be a "Pre-scan DB hit" and
        # preserve the old stamp.
        _schema, root, sig, _xver = db.get_meta()
        db.set_meta(root, sig, EXTRACTOR_VERSION - 1)
        db.conn.close()

        tri2 = Tricorder(root=tmpdir, db_path=db_path)
        tri2.get_ranked_tags([src], [])
        db2 = DBStore(db_path)
        try:
            self.assertEqual(db2.get_meta()[3], EXTRACTOR_VERSION)
            names = {r[2] for r in
                     db2.conn.execute("SELECT rel_file, line, name FROM tags")}
            self.assertIn('Renderer::render', names)
        finally:
            db2.conn.close()


if __name__ == '__main__':
    unittest.main()
