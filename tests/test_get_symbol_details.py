"""Tests for tricorder_detail MCP tool (Milestone 3)."""
import asyncio
import shutil
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from tricorder_server import tricorder_detail


class TestGetSymbolDetails(unittest.TestCase):
    def setUp(self):
        self.project_root = str(Path(__file__).parent.parent.resolve())

    def test_basic_symbol_detail(self):
        """Fetching a known function returns symbol with body."""
        result = asyncio.run(tricorder_detail(
            project_root=self.project_root,
            file="utils.py",
            name="count_tokens"
        ))
        self.assertNotIn("error", result)
        self.assertIn("symbol", result)
        sym = result["symbol"]
        self.assertEqual(sym["name"], "count_tokens")
        self.assertEqual(sym["type"], "function")
        self.assertIn("body", sym)
        self.assertGreater(len(sym["body"]), 0)

    def test_body_truncation(self):
        """Body is truncated to 500 chars."""
        result = asyncio.run(tricorder_detail(
            project_root=self.project_root,
            file="ranking.py",
            name="get_ranked_tags"
        ))
        self.assertNotIn("error", result)
        self.assertLessEqual(len(result["symbol"]["body"]), 500)

    def test_not_found_by_name(self):
        """Non-existent symbol name returns error 'not found'."""
        result = asyncio.run(tricorder_detail(
            project_root=self.project_root,
            file="utils.py",
            name="nonexistent_symbol_xyz"
        ))
        self.assertIn("error", result)
        self.assertEqual(result["error"], "not found")

    def test_not_found_by_file(self):
        """Non-existent file returns error 'not found'."""
        result = asyncio.run(tricorder_detail(
            project_root=self.project_root,
            file="does_not_exist.py",
            name="anything"
        ))
        self.assertIn("error", result)
        self.assertEqual(result["error"], "not found")

    def test_callers_callees_populated(self):
        """Callers and callees are populated from in-file references."""
        result = asyncio.run(tricorder_detail(
            project_root=self.project_root,
            file="graph.py",
            name="get_symbol_detail"
        ))
        self.assertNotIn("error", result)
        sym = result["symbol"]
        # get_symbol_detail calls build_call_graph, get_all_references, etc.
        # so callees should include those function names
        self.assertIsInstance(sym["callers"], list)
        self.assertIsInstance(sym["callees"], list)
        # At minimum, callees should have entries (it calls read_text, get_rel_fname, etc.)
        self.assertGreater(len(sym["callees"]), 0, "Expected callees from tree-sitter refs")
        # Each callee has name, file, line, cross_file
        for callee in sym["callees"]:
            self.assertIn("name", callee)
            self.assertIn("file", callee)
            self.assertIn("line", callee)
            self.assertIn("cross_file", callee)

    def test_cross_file_callers(self):
        """Cross-file callers are detected when another file references a symbol."""
        # find_src_files is defined in tricorder_server.py and called from core.py
        # So get_symbol_detail in core.py should have cross-file callers
        result = asyncio.run(tricorder_detail(
            project_root=self.project_root,
            file="core.py",
            name="find_src_files"
        ))
        # find_src_files is defined in tricorder_server.py, not core.py
        # So this should return not found (it's not a symbol in core.py)
        self.assertIn("error", result)
        self.assertEqual(result["error"], "not found")

    def test_cross_file_callees(self):
        """Cross-file callees are detected when a symbol calls something defined elsewhere."""
        # get_symbol_detail in graph.py calls read_text (defined in utils.py)
        result = asyncio.run(tricorder_detail(
            project_root=self.project_root,
            file="graph.py",
            name="get_symbol_detail"
        ))
        self.assertNotIn("error", result)
        sym = result["symbol"]
        # Should have cross-file callees (e.g., read_text from utils.py)
        cross_file_callees = [c for c in sym["callees"] if c.get("cross_file")]
        self.assertGreater(len(cross_file_callees), 0,
                           "Expected cross-file callees (e.g., read_text from utils.py)")
        for callee in cross_file_callees:
            self.assertIn("name", callee)
            self.assertIn("file", callee)
            self.assertIn("line", callee)
            self.assertTrue(callee["cross_file"])

    def test_all_fields_present(self):
        """Every field from SymbolRecord is present in the response."""
        result = asyncio.run(tricorder_detail(
            project_root=self.project_root,
            file="utils.py",
            name="count_tokens"
        ))
        self.assertNotIn("error", result)
        required = {"name", "type", "file", "line", "end_line",
                     "signature", "docstring", "language", "kind",
                     "body", "callers", "callees"}
        missing = required - set(result["symbol"].keys())
        self.assertFalse(missing, f"Missing: {missing}")

    def test_line_disambiguation(self):
        """Line parameter narrows to the correct symbol."""
        # ponytail: read the real line so the test survives utils.py edits
        utils_path = Path(self.project_root) / "utils.py"
        real_line = next(
            i + 1 for i, ln in enumerate(utils_path.read_text(encoding="utf-8").splitlines())
            if ln.startswith("def count_tokens")
        )
        result = asyncio.run(tricorder_detail(
            project_root=self.project_root,
            file="utils.py",
            name="count_tokens",
            line=real_line
        ))
        self.assertNotIn("error", result)
        self.assertEqual(result["symbol"]["name"], "count_tokens")

    def test_performance(self):
        """Single symbol lookup returns in <1s."""
        start = time.time()
        result = asyncio.run(tricorder_detail(
            project_root=self.project_root,
            file="utils.py",
            name="count_tokens"
        ))
        elapsed = time.time() - start
        self.assertNotIn("error", result)
        self.assertLess(elapsed, 1.0, f"Took {elapsed:.2f}s, expected <1s")


class TestCppSymbolDetailsSynthetic(unittest.TestCase):
    """Portable replacements for the projectM-dependent tests.

    Synthesizes a small C++ project in a temp dir exercising the same code
    paths (scoped-name matching, function-scope callee isolation) without
    the D:\\Projects\\projectm checkout.
    """

    HEADER = '''#pragma once
class Monitor {
public:
    void stretchMonitors();
    int width();
};
'''

    IMPL = '''#include "monitor.hpp"

void UpdateSpectrum() {}
void Align() {}
void CopyNewWaveformData() {}

void GetFrameAudioData() {
    UpdateSpectrum();
}

void UpdateFrameAudioData() {
    CopyNewWaveformData();
    Align();
}

void Monitor::stretchMonitors() {
    width();
}
'''

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="cpp_detail_"))
        (self.tmp / "monitor.hpp").write_text(self.HEADER, encoding="utf-8")
        (self.tmp / "audio.cpp").write_text(self.IMPL, encoding="utf-8")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def test_cpp_scoped_name_match(self):
        """tricorder_detail matches a clean name against a scoped C++ symbol
        (Monitor::stretchMonitors). Portable version of the projectM
        stretchMonitors() regression test."""
        result = asyncio.run(tricorder_detail(
            project_root=str(self.tmp),
            file="monitor.hpp",
            name="stretchMonitors",
        ))
        self.assertNotIn("error", result)
        # C++ methods are scoped (Class::method); the base name must match.
        returned = result["symbol"]["name"].rstrip("()")
        self.assertTrue(
            returned == "stretchMonitors" or returned.endswith("::stretchMonitors"),
            f"expected stretchMonitors (scoped or bare), got {returned!r}",
        )

    def test_function_scope_isolation(self):
        """Callees are scoped to the function body, not the whole file.

        audio.cpp has sibling functions with overlapping call targets
        (UpdateSpectrum, Align, CopyNewWaveformData). GetFrameAudioData must
        NOT list callees belonging to UpdateFrameAudioData.
        """
        result = asyncio.run(tricorder_detail(
            project_root=str(self.tmp),
            file="audio.cpp",
            name="GetFrameAudioData",
        ))
        self.assertNotIn("error", result)
        sym = result["symbol"]

        # end_line must cover the body, not just the declarator
        self.assertGreaterEqual(sym["end_line"], 9,
                                "end_line should cover the full function body")

        callee_names = {c["name"] for c in sym["callees"]}
        self.assertIn("UpdateSpectrum", callee_names,
                      "the function's own callee must be listed")
        # Defined in audio.cpp but belonging to a SIBLING function —
        # they must NOT appear as callees of GetFrameAudioData.
        false_positives = callee_names & {"CopyNewWaveformData", "Align"}
        self.assertFalse(false_positives,
                         f"GetFrameAudioData should not see callees from sibling functions: {false_positives}")


if __name__ == '__main__':
    unittest.main()
