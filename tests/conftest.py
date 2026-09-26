"""Shared pytest fixtures and configuration for Tricorder tests.

Redirects pytest tmp_path to the workspace so sandboxed environments that
block the system temp dir (C:\\Users\\...\\AppData\\Local\\Temp) still work.
Every write stays inside D:\\Projects\\tricorder\\.
"""
import pytest
import re
import shutil
from pathlib import Path

_WORKSPACE = Path(__file__).resolve().parent.parent
_WORKSPACE_TMP = _WORKSPACE / ".pytest-tmp"
_WORKSPACE_TMP.mkdir(exist_ok=True)

# Windows forbids <>:"/\|?* and control chars in file names. Parametrized
# test IDs (e.g. test_x[repo?x]) are used verbatim as dir names below, so
# sanitize them — otherwise the tmp_path fixture itself crashes on Windows.
_UNSAFE_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


@pytest.fixture
def tmp_path(request):
    """Workspace-local replacement for pytest's tmp_path fixture."""
    import uuid
    safe_name = _UNSAFE_CHARS.sub("_", request.node.name)
    base = _WORKSPACE_TMP / f"{safe_name}-{uuid.uuid4().hex[:8]}"
    base.mkdir(parents=True, exist_ok=True)
    try:
        yield base
    finally:
        if base.exists():
            shutil.rmtree(base, ignore_errors=True)


def pytest_configure(config):
    """Also redirect stdlib tempfile so tempfile.mkdtemp() lands in workspace."""
    import tempfile
    tempfile.tempdir = str(_WORKSPACE_TMP)


@pytest.fixture(autouse=True)
def _hermetic_cache_home(tmp_path, monkeypatch):
    """Scope TRICORDER_CACHE_HOME per test so no test ever touches the real
    user-level default cache root (~/.cache/tricorder). Tests that exercise
    the default path explicitly (tests/test_cache_root_default.py) delenv
    the variable themselves."""
    monkeypatch.setenv("TRICORDER_CACHE_HOME", str(tmp_path / "tcache"))
    import utils
    monkeypatch.setattr(utils, "_CACHE_ROOT", None)


def pytest_sessionfinish(session, exitstatus):
    """Clean up the workspace temp dir after the full test session."""
    if _WORKSPACE_TMP.exists():
        shutil.rmtree(_WORKSPACE_TMP, ignore_errors=True)