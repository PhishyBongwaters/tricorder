import shutil
import tempfile
import unittest
from pathlib import Path
from utils import repo_budget

class TestBudgetParity(unittest.TestCase):
    def setUp(self):
        # Transportable: temp dir instead of a machine-specific absolute path.
        self.tmp = Path(tempfile.mkdtemp(prefix="budget_parity_"))
        (self.tmp / "test.py").write_text("x\ny")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_repo_budget_invariants(self):
        res = repo_budget(str(self.tmp), 0)
        self.assertEqual(res['savings_pct'], 0.0)
        self.assertIn('token_estimate', res)
        self.assertIn('full_repo_estimate', res)

    def test_savings_clamp_on_zero_repo(self):
        res = repo_budget(str(self.tmp), 1000)
        self.assertEqual(res['savings_pct'], 0.0)

    def test_savings_clamp_on_zero_token_limit(self):
        res = repo_budget(str(self.tmp), 0)
        self.assertEqual(res['savings_pct'], 0.0)

if __name__ == '__main__':
    unittest.main()
