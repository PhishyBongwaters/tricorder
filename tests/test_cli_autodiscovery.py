"""Issue #19: CLI auto-discovers source files when no paths/--other-files given.

Reproduces the turn-0 injection failure path: `tricorder --root X --tier 0 ...`
with no file specs previously produced "No repository map generated". Now it
auto-scans --root like the MCP server does.
"""
import subprocess
import sys
from pathlib import Path

CLI = str(Path(__file__).resolve().parent.parent / "tricorder.py")
_PY = "class Foo:\n    def bar(self):\n        return 1\n"


def _write_tree(base, files):
    for rel, content in files.items():
        p = base / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        # write as pathlib, not derived Path object
        (base / rel).write_text(content, encoding="utf-8")


def _run(tmp_path, *extra):
    return subprocess.run(
        [sys.executable, CLI, "--root", str(tmp_path), "--format", "json", *extra],
        capture_output=True, text=True,
    )


def test_autodiscover_no_paths(tmp_path):
    _write_tree(tmp_path, {"a.py": _PY, "sub/b.py": _PY})
    r = _run(tmp_path)
    assert r.returncode == 0, r.stderr
    assert r.stdout.count('"file"') >= 1
    assert "No repository map generated" not in r.stdout


def test_autodiscover_honors_max_files(tmp_path):
    _write_tree(tmp_path, {f"f{i}.py": _PY for i in range(5)})
    r = _run(tmp_path, "--max-files", "2")
    assert r.returncode == 0, r.stderr
    assert "capping to 2" in r.stderr


def test_autodiscover_honors_exclude_globs(tmp_path):
    _write_tree(tmp_path, {"src/a.py": _PY, "vendor/lib.py": _PY})
    r = _run(tmp_path, "--exclude-globs", "vendor/**")
    assert r.returncode == 0, r.stderr
    assert "vendor" not in r.stdout


def test_explicit_path_skips_autodiscover(tmp_path):
    _write_tree(tmp_path, {"keep.py": _PY, "extra.py": _PY})
    r = subprocess.run(
        [sys.executable, CLI, "--root", str(tmp_path), "keep.py", "--format", "json"],
        capture_output=True, text=True,
    )
    assert r.returncode == 0, r.stderr
    # explicit path path must not be hijacked, and auto-scan message must not appear
    assert "No explicit files provided" not in r.stderr
    assert "extra.py" not in r.stdout