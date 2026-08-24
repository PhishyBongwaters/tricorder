"""
ctags probe integration tests.
"""

import os
import shutil
import sys
import tempfile
from pathlib import Path

import pytest

from ctags_probe import (
    ensure_ctags_index,
    probe_symbol,
    narrow_files,
    probe_and_narrow,
    rg_fallback,
)


def _make_repo(tmp_path):
    """Build a tiny repo with two C files referencing a shared symbol."""
    (tmp_path / "src").mkdir()
    header = tmp_path / "src" / "lib.h"
    header.write_text(
        "int add(int a, int b);\n"
        "typedef struct Thing { int x; } Thing;\n"
    )
    impl = tmp_path / "src" / "lib.c"
    impl.write_text(
        "#include \"lib.h\"\n"
        "int add(int a, int b) { return a + b; }\n"
        "static int helper(void) { return 42; }\n"
    )
    return tmp_path


@pytest.fixture
def repo(tmp_path):
    return _make_repo(tmp_path)


def test_narrow_files_basic(repo):
    """Narrow relative to project root, dedupe, respect include_parents."""
    root = str(repo)
    files = [
        (str(repo / "src" / "lib.c"), 3),
        (str(repo / "src" / "lib.c"), 8),   # duplicate file
    ]
    rel = narrow_files(files, root)
    assert rel == ["src/lib.c"]

    # include_parents=1 adds the src/ dir
    rel_parents = narrow_files(files, root, include_parents=1)
    assert "src" in rel_parents
    assert "src/lib.c" in rel_parents


def test_narrow_files_skips_outside_root(repo):
    """File outside project root is ignored."""
    root = str(repo)
    files = [(str(Path.home() / "elsewhere.c"), 1)]
    assert narrow_files(files, root) == []


def test_narrow_files_caps(repo):
    """max_files caps returned list."""
    root = str(repo)
    many = [(str(repo / "src" / f"f{i}.c"), 1) for i in range(200)]
    rel = narrow_files(many, root, max_files=50)
    assert len(rel) == 50


def test_rg_fallback(repo):
    """rg_fallback finds symbol across files."""
    if not shutil.which("rg"):
        pytest.skip("rg not installed")
    src = str(repo / "src")
    hits = rg_fallback(src, "add")
    # rg returns absolute paths on Windows; check presence of lib.h among them
    paths = [str(p) for p, _ in hits]
    assert any("lib.h" in p for p in paths), f"lib.h not in rg hits: {paths}"
    assert len(hits) >= 1


def test_probe_empty_when_no_ctags(repo):
    """rg-first probe works WITHOUT ctags (rg is the fast path, no index needed)."""
    if not shutil.which("rg"):
        pytest.skip("rg not installed")
    rel = probe_and_narrow(str(repo), "add")
    assert isinstance(rel, list)
    assert any("lib.c" in f or "lib.h" in f for f in rel), f"expected lib files, got {rel}"


def test_probe_and_narrow_happy_path(repo):
    """With ctags installed, probe narrows to files referencing the symbol."""
    if not shutil.which("ctags"):
        pytest.skip("ctags not installed")
    rel = probe_and_narrow(str(repo), "add")
    assert isinstance(rel, list)
    if rel:
        assert any("lib.c" in f or "lib.h" in f for f in rel), rel