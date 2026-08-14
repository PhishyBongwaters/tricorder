"""Tests for utils.py"""
import os
import sys
import tempfile
import unittest
sys.path.insert(0, '.')
from utils import count_tokens, discover_src_files


class TestTokenCount(unittest.TestCase):
    def test_token_count_empty(self):
        self.assertEqual(count_tokens(''), 0)

    def test_token_count_short(self):
        result = count_tokens('hello world')
        self.assertIsInstance(result, int)
        self.assertGreater(result, 0)

    def test_token_count_long(self):
        long_text = 'hello world\n' * 1000
        self.assertIsInstance(count_tokens(long_text), int)


class TestDiscoverSrcFilesExcludeGlobs(unittest.TestCase):
    """ponytail: smallest check proving vendor/** filtering works."""

    def _fixture(self):
        tmp = tempfile.mkdtemp()
        rels = {
            'src/main.cpp': 'int main() {}\n',
            'src/util.hpp': 'class Util {};\n',
            'vendor/glm/vec.hpp': 'class Vec {};\n',
            'vendor/glm/mat.hpp': 'class Mat {};\n',
            'README.md': '# hi\n',
        }
        for rel, content in rels.items():
            p = os.path.join(tmp, rel)
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, 'w', encoding='utf-8') as f:
                f.write(content)
        return tmp

    def test_no_glob_includes_vendor(self):
        tmp = self._fixture()
        files = discover_src_files(tmp, use_gitignore=False)
        names = {os.path.relpath(f, tmp).replace(os.sep, '/') for f in files}
        self.assertNotIn('vendor/glm/vec.hpp', names)
        self.assertIn('src/main.cpp', names)

    def test_vendor_glob_excludes_vendor(self):
        tmp = self._fixture()
        files = discover_src_files(tmp, use_gitignore=False, exclude_globs=['vendor/**'])
        names = {os.path.relpath(f, tmp).replace(os.sep, '/') for f in files}
        self.assertIn('src/main.cpp', names)
        self.assertIn('src/util.hpp', names)
        self.assertNotIn('vendor/glm/vec.hpp', names)
        self.assertNotIn('vendor/glm/mat.hpp', names)


if __name__ == '__main__':
    unittest.main()