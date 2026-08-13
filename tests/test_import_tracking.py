"""Tests for import tracking and qualified name resolution."""

import os
import tempfile
import shutil
import unittest
from pathlib import Path

from repomap_class import RepoMap
from import_parser import parse_imports, ImportBinding
from name_resolver import NameResolver
from grep_ast.tsl import get_parser


class TestPythonImportParser(unittest.TestCase):
    """Test Python import parsing."""

    def test_simple_import(self):
        parser = get_parser('python')
        code = b'import os'
        bindings = parse_imports('/test.py', 'python', parser, code)
        self.assertEqual(len(bindings), 1)
        self.assertEqual(bindings[0].local_name, 'os')
        self.assertEqual(bindings[0].qualified_name, 'os')
        self.assertFalse(bindings[0].is_from_import)

    def test_from_import(self):
        parser = get_parser('python')
        code = b'from pathlib import Path'
        bindings = parse_imports('/test.py', 'python', parser, code)
        self.assertEqual(len(bindings), 1)
        self.assertEqual(bindings[0].local_name, 'Path')
        self.assertEqual(bindings[0].qualified_name, 'pathlib.Path')
        self.assertTrue(bindings[0].is_from_import)

    def test_aliased_import(self):
        parser = get_parser('python')
        code = b'import os.path as osp'
        bindings = parse_imports('/test.py', 'python', parser, code)
        self.assertEqual(len(bindings), 1)
        self.assertEqual(bindings[0].local_name, 'osp')
        self.assertEqual(bindings[0].qualified_name, 'os.path')

    def test_aliased_from_import(self):
        parser = get_parser('python')
        code = b'from collections import OrderedDict as OD'
        bindings = parse_imports('/test.py', 'python', parser, code)
        self.assertEqual(len(bindings), 1)
        self.assertEqual(bindings[0].local_name, 'OD')
        self.assertEqual(bindings[0].qualified_name, 'collections.OrderedDict')

    def test_multiple_imports(self):
        parser = get_parser('python')
        code = b'import sys, json'
        bindings = parse_imports('/test.py', 'python', parser, code)
        self.assertEqual(len(bindings), 2)
        names = {b.local_name for b in bindings}
        self.assertEqual(names, {'sys', 'json'})

    def test_star_import(self):
        parser = get_parser('python')
        code = b'from os import *'
        bindings = parse_imports('/test.py', 'python', parser, code)
        self.assertEqual(len(bindings), 1)
        self.assertTrue(bindings[0].is_star)
        self.assertEqual(bindings[0].local_name, '*')


class TestJavaScriptImportParser(unittest.TestCase):
    """Test JS/TS import parsing."""

    def test_default_import(self):
        parser = get_parser('javascript')
        code = b"import foo from './foo';"
        bindings = parse_imports('/test.js', 'javascript', parser, code)
        self.assertEqual(len(bindings), 1)
        self.assertEqual(bindings[0].local_name, 'foo')

    def test_named_imports(self):
        parser = get_parser('javascript')
        code = b"import { bar, baz as b } from './bar';"
        bindings = parse_imports('/test.js', 'javascript', parser, code)
        self.assertEqual(len(bindings), 2)
        names = {b.local_name for b in bindings}
        self.assertEqual(names, {'bar', 'b'})

    def test_namespace_import(self):
        parser = get_parser('javascript')
        code = b"import * as ns from './namespace';"
        bindings = parse_imports('/test.js', 'javascript', parser, code)
        self.assertEqual(len(bindings), 1)
        self.assertEqual(bindings[0].local_name, 'ns')

    def test_require(self):
        parser = get_parser('javascript')
        code = b"const x = require('./module');"
        bindings = parse_imports('/test.js', 'javascript', parser, code)
        self.assertEqual(len(bindings), 1)
        self.assertEqual(bindings[0].local_name, 'x')

    def test_destructured_require(self):
        parser = get_parser('javascript')
        code = b"const { a, b: c } = require('./destructure');"
        bindings = parse_imports('/test.js', 'javascript', parser, code)
        self.assertEqual(len(bindings), 2)
        names = {b.local_name for b in bindings}
        self.assertEqual(names, {'a', 'c'})


class TestJavaImportParser(unittest.TestCase):
    """Test Java import parsing."""

    def test_simple_import(self):
        parser = get_parser('java')
        code = b'import java.util.List;'
        bindings = parse_imports('/test.java', 'java', parser, code)
        self.assertEqual(len(bindings), 1)
        self.assertEqual(bindings[0].local_name, 'List')
        self.assertEqual(bindings[0].qualified_name, 'java.util.List')

    def test_star_import(self):
        parser = get_parser('java')
        code = b'import java.util.*;'
        bindings = parse_imports('/test.java', 'java', parser, code)
        self.assertEqual(len(bindings), 1)
        self.assertTrue(bindings[0].is_star)


class TestCppImportParser(unittest.TestCase):
    """Test C++ import parsing."""

    def test_system_include(self):
        parser = get_parser('cpp')
        code = b'#include <iostream>'
        bindings = parse_imports('/test.cpp', 'cpp', parser, code)
        self.assertEqual(len(bindings), 1)
        self.assertEqual(bindings[0].local_name, 'iostream')

    def test_local_include(self):
        parser = get_parser('cpp')
        code = b'#include "myheader.h"'
        bindings = parse_imports('/test.cpp', 'cpp', parser, code)
        self.assertEqual(len(bindings), 1)
        self.assertEqual(bindings[0].local_name, 'myheader')

    def test_using_declaration(self):
        parser = get_parser('cpp')
        code = b'using namespace std;'
        bindings = parse_imports('/test.cpp', 'cpp', parser, code)
        self.assertEqual(len(bindings), 1)
        self.assertEqual(bindings[0].local_name, 'std')

    def test_alias_declaration(self):
        parser = get_parser('cpp')
        code = b'using MyAlias = MyRealClass;'
        bindings = parse_imports('/test.cpp', 'cpp', parser, code)
        self.assertEqual(len(bindings), 1)
        self.assertEqual(bindings[0].local_name, 'MyAlias')
        self.assertEqual(bindings[0].qualified_name, 'MyRealClass')


class TestNameResolver(unittest.TestCase):
    """Test name resolution via import bindings."""

    def test_single_candidate(self):
        resolver = NameResolver()
        resolver.add_file('/app.py', [
            ImportBinding('Path', 'pathlib.Path', '/app.py', 'pathlib', True, line=1),
        ])
        r = resolver.resolve('Path', '/app.py')
        self.assertEqual(r.qualified_name, 'pathlib.Path')
        self.assertEqual(r.confidence, 1.0)

    def test_unresolved(self):
        resolver = NameResolver()
        r = resolver.resolve('NonExistent', '/app.py')
        self.assertEqual(r.qualified_name, 'NonExistent')
        self.assertEqual(r.confidence, 0.0)

    def test_multiple_candidates(self):
        resolver = NameResolver()
        resolver.add_file('/app.py', [
            ImportBinding('Path', 'pathlib.Path', '/app.py', 'pathlib', True, line=1),
            ImportBinding('Path', 'mypackage.Path', '/other.py', 'mypackage', True, line=2),
        ])
        r = resolver.resolve('Path', '/app.py')
        # Should pick one (shortest qualified name)
        self.assertIn(r.qualified_name, ['pathlib.Path', 'mypackage.Path'])
        self.assertGreater(r.confidence, 0)

    def test_same_file_priority(self):
        resolver = NameResolver()
        resolver.add_file('/app.py', [
            ImportBinding('Path', 'pathlib.Path', '/app.py', 'pathlib', True, line=1),
            ImportBinding('Path', 'mypackage.Path', '/app.py', 'mypackage', True, line=2),
        ])
        r = resolver.resolve('Path', '/app.py')
        # Same file, multiple candidates — should still disambiguate
        self.assertGreater(r.confidence, 0)

    def test_local_scope_wins_over_global(self):
        """File B imports Path from mypackage; global scope also has pathlib.Path.
        Resolution in B should return mypackage.Path, not pathlib.Path."""
        resolver = NameResolver()
        # File A imports pathlib.Path
        resolver.add_file('/a.py', [
            ImportBinding('Path', 'pathlib.Path', '/a.py', 'pathlib', True, line=1),
        ])
        # File B imports mypackage.Path
        resolver.add_file('/b.py', [
            ImportBinding('Path', 'mypackage.Path', '/b.py', 'mypackage', True, line=1),
        ])
        # Resolving in B should use B's local import
        r = resolver.resolve('Path', '/b.py')
        self.assertEqual(r.qualified_name, 'mypackage.Path')
        self.assertEqual(r.confidence, 1.0)

    def test_local_scope_single_match_definitive(self):
        """Single local import is definitive even when global has conflicts."""
        resolver = NameResolver()
        resolver.add_file('/a.py', [
            ImportBinding('Path', 'pathlib.Path', '/a.py', 'pathlib', True, line=1),
            ImportBinding('Path', 'other.Path', '/c.py', 'other', True, line=1),
        ])
        resolver.add_file('/b.py', [
            ImportBinding('Path', 'mypackage.Path', '/b.py', 'mypackage', True, line=1),
        ])
        r = resolver.resolve('Path', '/b.py')
        self.assertEqual(r.qualified_name, 'mypackage.Path')
        self.assertEqual(r.confidence, 1.0)


class TestImportTrackingIntegration(unittest.TestCase):
    """Test import tracking integrated with RepoMap."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.repo = RepoMap(root=self.test_dir, verbose=False)

    def tearDown(self):
        if hasattr(self.repo, 'TAGS_CACHE') and hasattr(self.repo.TAGS_CACHE, 'close'):
            try:
                self.repo.TAGS_CACHE.close()
            except Exception:
                pass
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_cross_file_resolution_with_imports(self):
        """Test that qualified names resolve across files."""
        # Create file A that defines Path
        file_a = os.path.join(self.test_dir, 'defs.py')
        with open(file_a, 'w') as f:
            f.write('''
class Path:
    def __init__(self, p):
        self.p = p

def join(a, b):
    return a + b
''')

        # Create file B that imports and uses Path
        file_b = os.path.join(self.test_dir, 'app.py')
        with open(file_b, 'w') as f:
            f.write('''
from defs import Path, join

def main():
    p = Path("/tmp")
    result = join("a", "b")
    return p
''')

        # Build cross-file index
        defs, refs = self.repo._build_cross_file_index()

        # Path should be found as a definition
        self.assertIn('Path', defs)
        path_defs = defs['Path']
        self.assertTrue(any('defs.py' in d[0] for d in path_defs))

        # References to Path in app.py should be indexed
        self.assertIn('Path', refs)
        path_refs = refs['Path']
        self.assertTrue(any('app.py' in r[0] for r in path_refs))

    def test_qualified_name_resolution(self):
        """Test that qualified names are used when imports exist."""
        # Create file with a class definition
        file_a = os.path.join(self.test_dir, 'models.py')
        with open(file_a, 'w') as f:
            f.write('''
class User:
    def save(self):
        pass

class Product:
    def save(self):
        pass
''')

        # Create file that imports User
        file_b = os.path.join(self.test_dir, 'app.py')
        with open(file_b, 'w') as f:
            f.write('''
from models import User

def create():
    u = User()
    u.save()
''')

        # Build import index
        import_data = self.repo._build_import_index()
        resolver = import_data['resolver']

        # User should resolve to models.User
        r = resolver.resolve('User', file_b)
        self.assertEqual(r.qualified_name, 'models.User')
        self.assertEqual(r.confidence, 1.0)

    def test_import_index_memoized(self):
        """_build_import_index should return the same object on repeated calls."""
        d1 = self.repo._build_import_index()
        d2 = self.repo._build_import_index()
        self.assertIs(d1, d2, "second _build_import_index call should hit cache")


class TestRustImportParser(unittest.TestCase):
    """Test Rust import parsing."""

    def test_simple_use(self):
        parser = get_parser('rust')
        code = b'use std::fs::File;'
        bindings = parse_imports('/test.rs', 'rust', parser, code)
        self.assertEqual(len(bindings), 1)
        self.assertEqual(bindings[0].local_name, 'File')
        self.assertEqual(bindings[0].qualified_name, 'std::fs::File')

    def test_use_with_alias(self):
        parser = get_parser('rust')
        code = b'use std::fs::File as FsFile;'
        bindings = parse_imports('/test.rs', 'rust', parser, code)
        self.assertEqual(len(bindings), 1)
        self.assertEqual(bindings[0].local_name, 'FsFile')
        self.assertEqual(bindings[0].qualified_name, 'std::fs::File')

    def test_glob_import(self):
        parser = get_parser('rust')
        code = b'use std::io::*;'
        bindings = parse_imports('/test.rs', 'rust', parser, code)
        self.assertEqual(len(bindings), 1)
        self.assertTrue(bindings[0].is_star)


class TestGoImportParser(unittest.TestCase):
    """Test Go import parsing."""

    def test_grouped_import(self):
        parser = get_parser('go')
        code = b'import (\n    "os"\n    "path/filepath"\n)'
        bindings = parse_imports('/test.go', 'go', parser, code)
        self.assertEqual(len(bindings), 2)
        names = {b.local_name for b in bindings}
        self.assertIn('os', names)
        self.assertIn('filepath', names)


if __name__ == '__main__':
    unittest.main()
