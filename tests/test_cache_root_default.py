"""Default cache root: user-level, never inside a repository checkout.

The old default (<install>/.tricorder) wrote tricorder state into the
tricorder repo itself when self-hosting from a source checkout. The default
is now $XDG_CACHE_HOME/tricorder, else ~/.cache/tricorder;
TRICORDER_CACHE_HOME still overrides. A legacy install-dir cache earns a
one-time stderr notice instead of being silently abandoned.
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import utils


def _default_resolution(monkeypatch, home):
    """Arrange for get_cache_root() to take the default (non-env) path."""
    monkeypatch.setattr(utils, "_CACHE_ROOT", None)
    monkeypatch.delenv("TRICORDER_CACHE_HOME", raising=False)
    monkeypatch.delenv("XDG_CACHE_HOME", raising=False)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))  # Path.home() on Windows


def _real_tmp_home():
    """A fake HOME outside the checkout, bypassing conftest's workspace
    tmp redirect (which would trivially place it under the install dir)."""
    import tempfile
    saved, tempfile.tempdir = tempfile.tempdir, None
    try:
        return Path(tempfile.mkdtemp(prefix="tc-home-"))
    finally:
        tempfile.tempdir = saved


def test_default_cache_root_is_user_level(monkeypatch, tmp_path):
    import shutil
    home = _real_tmp_home()
    try:
        _default_resolution(monkeypatch, home)
        root = utils.get_cache_root()
        assert root == (home / ".cache" / "tricorder").resolve()
        # Structural guarantee: the default is never inside the checkout.
        install = Path(utils.__file__).resolve().parent
        assert install not in root.parents
    finally:
        shutil.rmtree(home, ignore_errors=True)


def test_default_honors_xdg_cache_home(monkeypatch, tmp_path):
    monkeypatch.setattr(utils, "_CACHE_ROOT", None)
    monkeypatch.delenv("TRICORDER_CACHE_HOME", raising=False)
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "xdg"))
    root = utils.get_cache_root()
    assert root == (tmp_path / "xdg" / "tricorder").resolve()


def test_env_override_still_wins(monkeypatch, tmp_path):
    monkeypatch.setattr(utils, "_CACHE_ROOT", None)
    monkeypatch.setenv("TRICORDER_CACHE_HOME", str(tmp_path / "custom"))
    root = utils.get_cache_root()
    assert root == (tmp_path / "custom").resolve()


def test_legacy_install_cache_notice(monkeypatch, tmp_path, capsys):
    """A populated <install>/.tricorder earns a one-time stderr notice."""
    fake_install = tmp_path / "install"
    (fake_install / ".tricorder" / "db").mkdir(parents=True)
    (fake_install / ".tricorder" / "db" / "old.db").write_text("x")
    monkeypatch.setattr(utils, "_INSTALL_DIR", fake_install)
    home = tmp_path / "home"
    home.mkdir()
    _default_resolution(monkeypatch, home)
    root = utils.get_cache_root()
    err = capsys.readouterr().err
    assert "legacy" in err
    assert ".tricorder" in err
    assert str(root) in err
    # The notice fires once per process (memoized root), not per call.
    utils.get_cache_root()
    assert capsys.readouterr().err == ""


def test_no_legacy_cache_no_notice(monkeypatch, tmp_path, capsys):
    fake_install = tmp_path / "install"
    fake_install.mkdir()  # no .tricorder inside
    monkeypatch.setattr(utils, "_INSTALL_DIR", fake_install)
    home = tmp_path / "home"
    home.mkdir()
    _default_resolution(monkeypatch, home)
    utils.get_cache_root()
    assert capsys.readouterr().err == ""


def test_legacy_in_repo_db_helper(tmp_path):
    root = tmp_path / "proj"
    (root / ".tricorder" / "db").mkdir(parents=True)
    legacy = root / ".tricorder" / "db" / "proj.db"
    legacy.write_text("x")
    assert utils.legacy_in_repo_db(str(root)) == legacy
    assert utils.legacy_in_repo_db(str(tmp_path / "nodb")) is None
