"""1B escalation hints + 2A deterministic fuzzy (synonyms, edit distance)."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from tricorder_server import (_query_variants, _levenshtein, _tokenize,
                              _escalation_hint)


class TestFuzzyEscalation(unittest.TestCase):
    def test_synonym_variant(self):
        self.assertIn("fetch_data", _query_variants("get_data"))

    def test_levenshtein(self):
        self.assertEqual(_levenshtein("pack", "pack"), 0)
        self.assertEqual(_levenshtein("serial", "serialize"), 3)
        self.assertGreater(_levenshtein("abc", "xyzzy"), 2)

    def test_tokenize(self):
        self.assertEqual(_tokenize("GetFrameAudio"), ["get", "frame", "audio"])

    def test_escalation_empty(self):
        esc = _escalation_hint("detect", "nosuchsym", 0, False)
        self.assertEqual(esc["next_rung"], "symbols")
        self.assertEqual(esc["reason"], "empty")

    def test_escalation_fuzzy(self):
        esc = _escalation_hint("symbols", "getdata", 3, True)
        self.assertEqual(esc["next_rung"], "detail")
        self.assertEqual(esc["reason"], "fuzzy_verify")

    def test_escalation_none(self):
        self.assertIsNone(_escalation_hint("detect", "count_tokens", 2, False))


if __name__ == "__main__":
    unittest.main()
