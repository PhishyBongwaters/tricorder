"""default_map_budget: scaled map budget with a mandated floor.

Companion to tests/test_map_budget.py (which pins the cap itself):
this file pins the AUTO default only.

- Floor is 2048 (minimum useful map), never below.
- Above the floor, budget scales linearly with repo size so huge repos
  don't get a postage-stamp slice: budget = max(floor, ceil(n * ratio)).
- Ratio defaults to 0.5 tok/file (~old 8192 default at Go scale);
  env TRICORDER_MAP_BUDGET_RATIO / TRICORDER_MAP_BUDGET_FLOOR retune
  without code changes. Explicit budgets always win (auto applies only
  when the caller passes nothing).
"""
import os
import sys
import unittest
sys.path.insert(0, '.')
from utils import default_map_budget, MAP_BUDGET_FLOOR


class TestScaledMapBudget(unittest.TestCase):
    def test_floor(self):
        self.assertEqual(default_map_budget(0), 2048)
        self.assertEqual(default_map_budget(200), 2048)
        self.assertGreaterEqual(MAP_BUDGET_FLOOR, 2048)

    def test_scales_with_size(self):
        small = default_map_budget(100)
        big = default_map_budget(16000)
        self.assertGreater(big, small)
        self.assertEqual(big, 8000)  # 0.5 * 16000; ~old 8192 at Go scale

    def test_ratio_env_override(self):
        os.environ["TRICORDER_MAP_BUDGET_RATIO"] = "1.0"
        try:
            self.assertEqual(default_map_budget(3000), 3000)
        finally:
            del os.environ["TRICORDER_MAP_BUDGET_RATIO"]

    def test_floor_env_override_respects_mandate(self):
        # Floor can be raised, never lowered below 2048.
        os.environ["TRICORDER_MAP_BUDGET_FLOOR"] = "100"
        try:
            self.assertEqual(default_map_budget(10), 2048)
        finally:
            del os.environ["TRICORDER_MAP_BUDGET_FLOOR"]
        os.environ["TRICORDER_MAP_BUDGET_FLOOR"] = "4096"
        try:
            self.assertEqual(default_map_budget(10), 4096)
        finally:
            del os.environ["TRICORDER_MAP_BUDGET_FLOOR"]


if __name__ == "__main__":
    unittest.main()
