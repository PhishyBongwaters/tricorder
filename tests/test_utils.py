"""Tests for utils.py"""
import sys
import unittest
sys.path.insert(0, '.')
from utils import count_tokens


class TestTokenCount(unittest.TestCase):
    def test_token_count_empty(self):
        self.assertEqual(count_tokens(''), 0)

    def test_token_count_short(self):
        result = count_tokens('hello world')
        self.assertIsInstance(result, int)
        self.assertGreater(result, 0)

    def test_token_count_long(self):
        long_text = 'hello world\n' * 1000
        result = count_tokens(long_text)
        self.assertIsInstance(result, int)
        self.assertGreater(result, 0)


if __name__ == '__main__':
    unittest.main()
