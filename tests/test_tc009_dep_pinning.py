"""Regression test for TC-009: dependency pinning (structural)."""
from pathlib import Path
import re

REQ = Path(__file__).resolve().parent.parent / "requirements.txt"


def test_all_dependencies_pinned():
    # TC-009: every runtime dependency is version-pinned (no floating ranges).
    unpinned = []
    for line in REQ.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        name, _, spec = line.partition("==")
        if not spec or not re.fullmatch(r"[0-9][0-9A-Za-z.]*", spec):
            unpinned.append(line)
    assert unpinned == [], f"unpinned deps violate TC-009: {unpinned}"
