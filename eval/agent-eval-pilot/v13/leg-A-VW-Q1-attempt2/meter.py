#!/usr/bin/env python3
"""Meter A-VW-Q1 attempt 2 from the returned command list (5 CLI + 2 reads)."""
import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))
from utils import count_tokens

PY = r"D:\Projects\tricorder\.venv\Scripts\python.exe"
CLI = str(Path(__file__).resolve().parents[4] / "tricorder.py")
ROOT = r"D:\Projects\Tricorder-Testing-Repos\vaultwarden"
OUT = Path(__file__).resolve().parent


def run_cli(*args):
    p = subprocess.run([PY, CLI, "--root", ROOT, *args],
                       capture_output=True, text=True, encoding="utf-8")
    return p.stdout


def read_range(rel, start, end):
    lines = (Path(ROOT) / rel).read_text(encoding="utf-8").splitlines()
    return "\n".join(lines[start - 1:end])


parts = {}
parts["step_probe.txt"] = run_cli("--probe-digest", "--format", "json")
parts["step_detect_totpverify.txt"] = run_cli(
    "--detect", "totp_verify", "--format", "json", "--max-results", "5")
parts["step_detect_totp.txt"] = run_cli(
    "--detect", "totp", "--format", "json", "--max-results", "5")
parts["step_symbols_validatetotp.txt"] = run_cli(
    "--symbols", "validate_totp_code", "--format", "json", "--max-results", "5")
parts["step_tier1.txt"] = run_cli(
    "--tier", "1", "--context-lines", "3", "--format", "json",
    "--max-results", "5")
parts["step_read_auth101_185.txt"] = read_range(
    "src/api/core/two_factor/authenticator.rs", 101, 185)
parts["step_read_ident820_839.txt"] = read_range(
    "src/api/identity.rs", 820, 839)

total = 0
table = {}
for name, text in parts.items():
    (OUT / name).write_text(text, encoding="utf-8")
    tk = count_tokens(text)
    total += tk
    table[name] = tk
    print(f"{name}: {tk} tokens")
print(f"TOTAL: {total} tokens")
(OUT / "meter.json").write_text(json.dumps(table, indent=1))
