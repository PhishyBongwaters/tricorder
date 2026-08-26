"""Shared pytest fixtures and configuration for Tricorder tests.

Redirects pytest tmp_path to the workspace so sandboxed environments that
block the system temp dir (C:\\Users\\...\\AppData\\Local\\Temp) still work.
Every write stays inside D:\\Projects\\tricorder\\.
"""
import pytest
import shutil
from pathlib import Path

_WORKSPACE = Path(__file__).resolve().parent.parent
_WORKSPACE_TMP = _WORKSPACE / ".pytest-tmp"
_WORKSPACE_TMP.mkdir(exist_ok=True)


@pytest.fixture
def tmp_path(request):
    """Workspace-local replacement for pytest's tmp_path fixture."""
    import uuid
    base = _WORKSPACE_TMP / f"{request.node.name}-{uuid.uuid4().hex[:8]}"
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


def pytest_sessionfinish(session, exitstatus):
    """Clean up the workspace temp dir after the full test session."""
    if _WORKSPACE_TMP.exists():
        shutil.rmtree(_WORKSPACE_TMP, ignore_errors=True)