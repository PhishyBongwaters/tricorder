"""M0.9.1 — Token Budget Fields in MCP Responses.

Every MCP tool returns token_estimate, full_repo_estimate, savings_pct.
"""
import asyncio
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from tricorder_server import (
    tricorder_scan, tricorder_symbols, tricorder_detect, tricorder_detail,
)


def _check_budget(obj):
    """Assert the 3 budget fields exist, are sensibly shaped in obj (dict)."""
    assert "token_estimate" in obj, "missing token_estimate"
    assert "full_repo_estimate" in obj, "missing full_repo_estimate"
    assert "savings_pct" in obj, "missing savings_pct"
    assert isinstance(obj["token_estimate"], int) and obj["token_estimate"] >= 0
    assert isinstance(obj["full_repo_estimate"], int) and obj["full_repo_estimate"] >= 0
    assert isinstance(obj["savings_pct"], float) and 0 <= obj["savings_pct"] <= 100


class TestTokenBudgetFields(unittest.TestCase):
    def setUp(self):
        self.project_root = str(Path(__file__).parent.parent.resolve())

    def test_scan(self):
        r = asyncio.run(tricorder_scan(
            project_root=self.project_root, token_limit=4096, dry_run=True))
        self.assertNotIn("error", r)
        _check_budget(r)

    def test_scan_output_file(self):
        import tempfile, shutil
        tmpdir = tempfile.mkdtemp(prefix="tb_")
        self.addCleanup(shutil.rmtree, tmpdir, True)
        out = str(Path(tmpdir) / "map.txt")
        r = asyncio.run(tricorder_scan(
            project_root=self.project_root, token_limit=4096,
            tier=0, output_file=out))
        self.assertNotIn("error", r)
        _check_budget(r)

    def test_scan_inline(self):
        r = asyncio.run(tricorder_scan(
            project_root=self.project_root, token_limit=1024, tier=0))
        self.assertNotIn("error", r)
        _check_budget(r)

    def test_detect(self):
        r = asyncio.run(tricorder_detect(
            project_root=self.project_root, query="count_tokens"))
        self.assertNotIn("error", r)
        _check_budget(r)

    def test_symbols(self):
        r = asyncio.run(tricorder_symbols(
            project_root=self.project_root, query="count_tokens"))
        self.assertNotIn("error", r)
        _check_budget(r)

    def test_detail(self):
        r = asyncio.run(tricorder_detail(
            project_root=self.project_root, file="utils.py", name="count_tokens"))
        self.assertNotIn("error", r)
        _check_budget(r)


if __name__ == '__main__':
    unittest.main()