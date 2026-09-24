#!/usr/bin/env python3
"""Meter A-Vue-Q1 attempt 1 from the recalled command list (13 calls)."""
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


def cli(*args):
    p = subprocess.run([PY, CLI, "--root", ROOT, *args],
                       capture_output=True, text=True, encoding="utf-8")
    return p.stdout


def read_range(path, start, end):
    lines = path.read_text(encoding="utf-8").splitlines()
    return "\n".join(lines[start - 1:end])


IDX = OB / "index.ts"
parts = {}
parts["step_map.txt"] = cli("--format", "json", "--map-tokens", "2048")
parts["step_detect_defreact.txt"] = cli("--format", "json", "--detect",
                                        "defineReactive", "--max-results", "5")
parts["step_detect_dep.txt"] = cli("--format", "json", "--detect", "Dep",
                                   "--max-results", "5")
parts["step_detect_watcher.txt"] = cli("--format", "json", "--detect",
                                       "Watcher", "--max-results", "5")
parts["step_read_idx128_247.txt"] = read_range(IDX, 128, 247)
parts["step_read_dep1_108.txt"] = read_range(OB / "dep.ts", 1, 108)
parts["step_read_watcher1_240.txt"] = read_range(OB / "watcher.ts", 1, 240)
parts["step_detect_observe.txt"] = cli("--format", "json", "--detect",
                                       "observe", "--max-results", "5")
parts["step_read_idx1_80.txt"] = read_range(IDX, 1, 80)
parts["step_read_state1_120.txt"] = read_range(
    Path(ROOT) / "src" / "core" / "instance" / "state.ts", 1, 120)
parts["step_read_state121_200.txt"] = read_range(
    Path(ROOT) / "src" / "core" / "instance" / "state.ts", 121, 200)
parts["step_read_sched1_120.txt"] = read_range(OB / "scheduler.ts", 1, 120)
parts["step_read_sched121_199.txt"] = read_range(OB / "scheduler.ts", 121, 199)

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
