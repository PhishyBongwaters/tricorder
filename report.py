"""FileReport dataclass — extracted from core.py (SPEC_db_map Goal 2/5)."""

from typing import Dict, List


class FileReport:
    excluded: Dict[str, str]        # File -> exclusion reason with status
    definition_matches: int         # Total definition tags
    reference_matches: int          # Total reference tags
    total_files_considered: int     # Total files provided as input
    untagged_files: List[str] = None # Files with no tree-sitter symbols
    coverage_pct: float = 100.0      # % of source files represented in map (issue #18)

    def __init__(
        self,
        excluded: Dict[str, str],
        definition_matches: int,
        reference_matches: int,
        total_files_considered: int,
        untagged_files: List[str] = None,
        coverage_pct: float = 100.0,
    ):
        self.excluded = excluded
        self.definition_matches = definition_matches
        self.reference_matches = reference_matches
        self.total_files_considered = total_files_considered
        self.untagged_files = untagged_files
        self.coverage_pct = coverage_pct
