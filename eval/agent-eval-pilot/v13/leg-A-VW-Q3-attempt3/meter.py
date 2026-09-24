#!/usr/bin/env python3
"""Meter A-VW-Q3 attempt 3 from the recalled command list (6 CLI + 4 reads)."""
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
parts["step_smartmap.txt"] = run_cli("--smart-map", "is_coll_manageable_by_user",
                                     "--format", "json", "--max-results", "5")
parts["step_detect.txt"] = run_cli("--detect", "is_coll_manageable_by_user",
                                   "--format", "json", "--max-results", "5")
parts["step_read_collection_570_689.txt"] = read_range(
    "src/db/models/collection.rs", 570, 689)
parts["step_read_auth_881_900.txt"] = read_range("src/auth.rs", 881, 900)
parts["step_read_auth_963_982.txt"] = read_range("src/auth.rs", 963, 982)
parts["step_symbols.txt"] = run_cli("--symbols", "is_coll_manageable_by_user",
                                    "--format", "json", "--max-results", "10")

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