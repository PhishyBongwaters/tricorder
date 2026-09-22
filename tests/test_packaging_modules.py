"""Packaging guard: every top-level app module ships in the install.

`pip install -e .` only installs modules listed in pyproject
[tool.setuptools] py-modules. Anything missing imports fine from the repo
root (cwd on sys.path, which is how pytest sees it) but breaks for
installed console scripts run elsewhere. This test fails the suite if a
new module is added without listing it — same pattern as TC-009.
"""
import tomllib
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def test_all_top_level_modules_packaged():
    with open(REPO / "pyproject.toml", "rb") as f:
        pyproject = tomllib.load(f)
    listed = set(pyproject["tool"]["setuptools"]["py-modules"])
    actual = {p.stem for p in REPO.glob("*.py")}
    missing = sorted(actual - listed)
    assert missing == [], (
        f"top-level modules missing from pyproject py-modules: {missing} "
        f"(installed console scripts would ImportError outside the repo root)")


def test_listed_modules_exist():
    with open(REPO / "pyproject.toml", "rb") as f:
        pyproject = tomllib.load(f)
    listed = pyproject["tool"]["setuptools"]["py-modules"]
    phantom = [m for m in listed if not (REPO / f"{m}.py").exists()]
    assert phantom == [], f"py-modules lists files that do not exist: {phantom}"


if __name__ == "__main__":
    test_all_top_level_modules_packaged()
    test_listed_modules_exist()
    print("packaging OK")
