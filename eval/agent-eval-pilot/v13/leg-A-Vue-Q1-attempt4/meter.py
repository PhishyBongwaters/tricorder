#!/usr/bin/env python3
"""Meter A-Vue-Q1 attempt 4 from the returned command list (8 steps)."""
import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))
from utils import count_tokens

PY = r"D:\Projects\tricorder\.venv\Scripts\python.exe"
CLI = str(Path(__file__).resolve().parents[4] / "tricorder.py")
ROOT = r"D:\Projects\Tricorder-Testing-Repos\vue"
OB = Path(ROOT) / "src" / "core" / "observer"
OUT = Path(__file__).resolve().parent


def run_cli(*args):
    p = subprocess.run([PY, CLI, "--root", ROOT, *args],
                       capture_output=True, text=True, encoding="utf-8")
    return p.stdout


def read_range(path, start, end):
    lines = path.read_text(encoding="utf-8").splitlines()
    return "\n".join(lines[start - 1:end])


parts = {}
parts["step_probe.txt"] = run_cli("--probe-digest", "--format", "json")
parts["step_detect_reactive.txt"] = run_cli("--detect", "reactive",
                                            "--format", "json",
                                            "--max-results", "5")
parts["step_read_idx128_247.txt"] = read_range(OB / "index.ts", 128, 247)
parts["step_read_reactive1_120.txt"] = read_range(
    Path(ROOT) / "src" / "v3" / "reactivity" / "reactive.ts", 1, 120)
parts["step_read_dep1_100.txt"] = read_range(OB / "dep.ts", 1, 100)
parts["step_read_watcher1_120.txt"] = read_range(OB / "watcher.ts", 1, 120)
parts["step_read_watcher120_239.txt"] = read_range(OB / "watcher.ts", 120, 239)
parts["step_read_idx1_127.txt"] = read_range(OB / "index.ts", 1, 127)

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
