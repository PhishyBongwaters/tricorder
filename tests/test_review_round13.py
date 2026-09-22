"""Round 13 review: --diff must not report symlinks as phantom additions.

The scan path resolves symlinks (Path.resolve()) before storing rel
names, but diff_against_index compared raw discovery paths against the
stored rels — so a symlink to an already-indexed file reported as
"Added" on EVERY --diff run, even with zero changes.
"""
import os
import subprocess
import sys
from pathlib import Path

import pytest

_CLI = str(Path(__file__).resolve().parent.parent / "tricorder.py")
_PYBIN = sys.executable


def _cli_run(root, *args):
    # Hermetic cache root: the canonical DB now lives in the cache, and the
    # default cache is shared across tests — "proj.db" would collide.
    cache = Path(root).parent / "tcache"
    env = dict(os.environ, TRICORDER_CACHE_HOME=str(cache))
    return subprocess.run([_PYBIN, _CLI, "--root", str(root), "--quiet", *args],
                          capture_output=True, text=True, timeout=180, env=env)


def test_diff_symlink_not_phantom_added(tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    (root / "real.py").write_text("def real_fn():\n    return 1\n", encoding="utf-8")
    try:
        os.symlink("real.py", root / "link.py")
    except OSError:
        pytest.skip("symlinks unavailable")
    assert _cli_run(root, "--init").returncode == 0
    assert _cli_run(root).returncode == 0  # scan populates index
    r = _cli_run(root, "--diff")
    assert r.returncode == 0, r.stderr[-500:]
    assert "Added (0)" in r.stdout, \
        f"symlink to an indexed file must not report as added:\n{r.stdout}"
    # Stable across runs: no phantom delta ever appears.
    r2 = _cli_run(root, "--diff")
    assert "Added (0)" in r2.stdout
