"""FileReport dataclass — extracted from core.py (SPEC_db_map Goal 2/5)."""

from dataclasses import dataclass
from typing import Dict, List


@dataclass
class FileReport:
    excluded: Dict[str, str]        # File -> exclusion reason with status
    definition_matches: int         # Total definition tags
    reference_matches: int          # Total reference tags
    total_files_considered: int     # Total files provided as input
    untagged_files: List[str] = None # Files with no tree-sitter symbols
    coverage_pct: float = 100.0      # % of source files represented in map (issue #18)
