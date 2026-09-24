#!/usr/bin/env python3
"""Meter A-Vue-Q1 attempt 3 from the returned command list (11 steps)."""
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
parts["step_probe.txt"] = run_cli("--probe-digest")
parts["step_detect_defreact.txt"] = run_cli("--detect", "defineReactive",
                                            "--format", "json",
                                            "--max-results", "10")
parts["step_read_idx128_250.txt"] = read_range(OB / "index.ts", 128, 250)
parts["step_detect_classdep.txt"] = run_cli("--detect", "class Dep",
                                            "--format", "json",
                                            "--max-results", "5")
parts["step_read_dep1_100.txt"] = read_range(OB / "dep.ts", 1, 100)
parts["step_detect_watcher.txt"] = run_cli("--detect", "Watcher",
                                           "--format", "json",
                                           "--max-results", "10")
parts["step_read_watcher1_120.txt"] = read_range(OB / "watcher.ts", 1, 120)
parts["step_read_watcher121_240.txt"] = read_range(OB / "watcher.ts", 121, 240)
parts["step_symbols_observe.txt"] = run_cli("--symbols", "observe",
                                            "--format", "json",
                                            "--max-results", "5")
parts["step_read_idx104_128.txt"] = read_range(OB / "index.ts", 104, 128)
parts["step_read_idx48_97.txt"] = read_range(OB / "index.ts", 48, 97)

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
