"""Round 14 review: the scan path must not index files outside the repo root.

A symlink inside the repo pointing to a file OUTSIDE the root resolves
to an absolute path; get_rel_fname() then returns the absolute path
unchanged (relative_to raises ValueError -> fallback returns fname).
The scan stored that absolute path as the DB rel and rendered the
outside file's content in the map -- a host-path/data leak served by
CLI and MCP alike.

Expected: files resolving outside the root are skipped (with a
warning), never stored or rendered. The DB must contain only
repo-relative rels.
"""
import os
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
_PYBIN = sys.executable
_CLI = str(REPO / "tricorder.py")


def _cli_run(root, *args):
    return subprocess.run([_PYBIN, _CLI, "--root", str(root), "--quiet", *args],
                          capture_output=True, text=True, timeout=180)


def _canonical_db(root: Path) -> Path:
    return root / ".tricorder" / "db" / f"{root.name}.db"


def _rels(db_path: Path):
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        fs = [r[0] for r in con.execute("SELECT rel_file FROM file_state")]
        tags = [r[0] for r in con.execute("SELECT DISTINCT rel_file FROM tags")]
    finally:
        con.close()
    return fs, tags


def test_scan_skips_symlink_pointing_outside_root(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    (root / "a.py").write_text("x = 1\n", encoding="utf-8")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.py").write_text("def leaked_secret(): pass\n", encoding="utf-8")
    try:
        os.symlink(str(outside / "secret.py"), root / "link.py")
    except OSError:
        pytest.skip("symlinks unavailable")

    assert _cli_run(root, "--init").returncode == 0
    r = _cli_run(root)
    assert r.returncode == 0, r.stderr[-500:]
    assert "leaked_secret" not in r.stdout

    db = _canonical_db(root)
    fs, tags = _rels(db)
    assert fs, "expected file_state rows for in-repo files"
    assert all(not os.path.isabs(x) for x in fs), fs
    assert all(not os.path.isabs(x) for x in tags), tags
    assert not any("outside" in x for x in fs + tags), fs + tags


def test_scan_skips_symlinked_dir_pointing_outside_root(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    (root / "a.py").write_text("x = 1\n", encoding="utf-8")
    outside = tmp_path / "ext"
    outside.mkdir()
    (outside / "mod.py").write_text("def ext_fn(): pass\n", encoding="utf-8")
    try:
        os.symlink(str(outside), root / "extlink")
    except OSError:
        pytest.skip("symlinks unavailable")

    assert _cli_run(root, "--init").returncode == 0
    r = _cli_run(root)
    assert r.returncode == 0, r.stderr[-500:]
    assert "ext_fn" not in r.stdout


def test_diff_ignores_symlink_pointing_outside_root(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    (root / "a.py").write_text("x = 1\n", encoding="utf-8")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.py").write_text("def leaked_secret(): pass\n", encoding="utf-8")

    assert _cli_run(root, "--init").returncode == 0
    assert _cli_run(root).returncode == 0
    # Add the escaping symlink AFTER the scan; diff must not report it.
    try:
        os.symlink(str(outside / "secret.py"), root / "link.py")
    except OSError:
        pytest.skip("symlinks unavailable")

    r = _cli_run(root, "--diff")
    assert r.returncode == 0, r.stderr[-500:]
    assert "Added (0)" in r.stdout, \
        f"outside-root symlink must not report as added:\n{r.stdout}"


def _plugin_module():
    """Import plugins.tricorder with hermes config mocks isolated."""
    import importlib
    import types
    fake_cfg = {'plugins': {'entries': {'tricorder': {}}}}
    fake_mod = types.SimpleNamespace(load_config=lambda: fake_cfg)
    fake_home = types.SimpleNamespace(get_hermes_home=lambda: Path(tempfile.mkdtemp()))
    old_cfg = sys.modules.get('hermes_cli.config')
    old_home = sys.modules.get('hermes_constants')
    sys.modules['hermes_cli.config'] = fake_mod
    sys.modules['hermes_constants'] = fake_home
    plugin = importlib.import_module('plugins.tricorder')
    importlib.reload(plugin)

    def teardown():
        if old_cfg is None:
            sys.modules.pop('hermes_cli.config', None)
        else:
            sys.modules['hermes_cli.config'] = old_cfg
        if old_home is None:
            sys.modules.pop('hermes_constants', None)
        else:
            sys.modules['hermes_constants'] = old_home
    return plugin, teardown


def test_plugin_build_map_ignores_failed_scan(tmp_path):
    """A nonzero CLI exit is a failed scan: build_map must return None and
    must NOT write meta from a stale map file (fresh signature + stale
    content would make the stale cache look valid)."""
    import tempfile
    import types
    import unittest.mock as um

    plugin, teardown = _plugin_module()
    try:
        out = Path(tempfile.mkdtemp()) / "stale.map"
        out.write_text("STALE MAP CONTENT\n", encoding="utf-8")
        meta_file = Path(tempfile.mkdtemp()) / "meta.json"
        assert not meta_file.exists()

        def fake_run(cmd, *a, **k):
            return types.SimpleNamespace(returncode=1, stdout="",
                                         stderr="boom: scan failed")

        plugin._TRICORDER_CLI = "tricorder"
        plugin._cache_file = lambda root: out
        plugin._meta_file = lambda root: meta_file

        with um.patch.object(plugin.subprocess, 'run', side_effect=fake_run):
            result = plugin.build_map("/fake/project")

        assert result is None
        assert not meta_file.exists(), \
            "failed scan must not write meta from a stale map file"
    finally:
        teardown()


def test_scan_survives_symlink_loop(tmp_path):
    """A symlink loop (a.py -> b.py -> a.py) must not crash the scan with
    a raw RuntimeError traceback: the unresolvable files are skipped with
    a warning and the rest of the repo still maps."""
    root = tmp_path / "repo"
    root.mkdir()
    (root / "real.py").write_text("def real_fn():\n    return 1\n", encoding="utf-8")
    try:
        os.symlink("b.py", root / "a.py")
        os.symlink("a.py", root / "b.py")
    except OSError:
        pytest.skip("symlinks unavailable")

    assert _cli_run(root, "--init").returncode == 0
    r = _cli_run(root)
    assert r.returncode == 0, f"scan crashed on symlink loop:\n{r.stderr[-800:]}"
    assert "RuntimeError" not in r.stderr
    assert "Symlink loop" not in r.stderr
    # The healthy file still maps.
    assert "real_fn" in r.stdout

    db = _canonical_db(root)
    fs, _ = _rels(db)
    assert all(not os.path.isabs(x) for x in fs), fs
