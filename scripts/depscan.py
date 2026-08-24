#!/usr/bin/env python3
"""TC-009: dependency supply-chain hygiene.

Generates a pinned dependency inventory (name==version) for the active
environment and, if `pip-audit` is available, a vulnerability scan report.

Usage:
    python scripts/depscan.py            # write deps.inventory.txt
    python scripts/depscan.py --audit    # also run pip-audit -> deps.audit.json

The inventory is the source of truth that requirements.txt is pinned from.
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def write_inventory() -> None:
    """Dump the resolved dependency set (incl. transitive) as name==version."""
    try:
        from importlib import metadata
        pkgs = sorted(
            (f"{d.metadata['Name']}=={d.version}" for d in metadata.distributions()),
            key=str.lower,
        )
    except Exception as e:  # noqa: BLE001
        print(f"importlib.metadata failed: {e}", file=sys.stderr)
        sys.exit(1)
    inv = ROOT / "deps.inventory.txt"
    inv.write_text("\n".join(pkgs) + "\n", encoding="utf-8")
    print(f"Wrote {inv} ({len(pkgs)} packages)")


def run_audit() -> int:
    """Run pip-audit if installed; non-zero exits are reported, not fatal."""
    try:
        subprocess.check_call(
            [sys.executable, "-m", "pip_audit", "-r", str(ROOT / "requirements.txt"),
             "-f", "json", "-o", str(ROOT / "deps.audit.json")],
        )
        print("pip-audit: no known vulnerabilities.")
        return 0
    except FileNotFoundError:
        print("pip-audit not installed; run: pip install pip-audit")
        return 2
    except subprocess.CalledProcessError as e:
        print(f"pip-audit found issues (exit {e.returncode}); see deps.audit.json")
        return e.returncode


if __name__ == "__main__":
    write_inventory()
    if "--audit" in sys.argv:
        run_audit()
