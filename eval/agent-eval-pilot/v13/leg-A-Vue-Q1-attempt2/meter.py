#!/usr/bin/env python3
"""Meter A-Vue-Q1 attempt 2 from the recalled command list (15 steps)."""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))
from utils import count_tokens

PY = r"D:\Projects\tricorder\.venv\Scripts\python.exe"
CLI = str(Path(__file__).resolve().parents[4] / "tricorder.py")
ROOT = r"D:\Projects\Tricorder-Testing-Repos\vue"
OB = Path(ROOT) / "src" / "core" / "observer"
ST = Path(ROOT) / "src" / "core" / "instance" / "state.ts"
OUT = Path(__file__).resolve().parent


def cli(*args):
    p = subprocess.run([PY, CLI, "--root", ROOT, *args],
                       capture_output=True, text=True, encoding="utf-8")
    return p.stdout


def read_range(path, start, end):
    lines = path.read_text(encoding="utf-8").splitlines()
    return "\n".join(lines[start - 1:end])


def grep(path, pattern, limit=10):
    out = []
    for i, ln in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if re.search(pattern, ln):
            out.append(f"{i}:{ln}")
            if len(out) >= limit:
                break
    return "\n".join(out)


parts = {}
parts["step_map.txt"] = cli("--format", "json", "--map-tokens", "2048")
parts["step_detect_defreact.txt"] = cli("--format", "json", "--detect",
                                        "defineReactive", "--max-results", "5")
parts["step_detect_dep.txt"] = cli("--format", "json", "--detect", "Dep",
                                   "--max-results", "5")
parts["step_detect_watcher.txt"] = cli("--format", "json", "--detect",
                                       "Watcher", "--max-results", "5")
parts["step_detect_notify.txt"] = cli("--format", "json", "--detect",
                                      "notify", "--max-results", "5")
parts["step_read_idx128_247.txt"] = read_range(OB / "index.ts", 128, 247)
parts["step_read_dep1_90.txt"] = read_range(OB / "dep.ts", 1, 90)
parts["step_read_watcher1_120.txt"] = read_range(OB / "watcher.ts", 1, 120)
parts["step_read_watcher121_240.txt"] = read_range(OB / "watcher.ts", 121, 240)
parts["step_read_idx1_127.txt"] = read_range(OB / "index.ts", 1, 127)
parts["step_read_sched1_120.txt"] = read_range(OB / "scheduler.ts", 1, 120)
parts["step_read_sched121_240.txt"] = read_range(OB / "scheduler.ts", 121, 240)
parts["step_read_state90_120.txt"] = read_range(ST, 90, 120)
parts["step_grep_observe.txt"] = grep(ST, r"observe\(")
parts["step_read_state155_180.txt"] = read_range(ST, 155, 180)

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
