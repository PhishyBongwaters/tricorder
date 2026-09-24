#!/usr/bin/env python3
"""Meter A-Elixir-Q1 attempt 2 from the recalled command list (14 steps)."""
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
ROOT = r"D:\Projects\Tricorder-Testing-Repos\elixir"
GS = Path(ROOT) / "lib" / "elixir" / "lib" / "gen_server.ex"
OUT = Path(__file__).resolve().parent


def cli(*args):
    p = subprocess.run([PY, CLI, "--root", ROOT, *args],
                       capture_output=True, text=True, encoding="utf-8")
    return p.stdout


def read_range(start, end):
    lines = GS.read_text(encoding="utf-8").splitlines()
    return "\n".join(lines[start - 1:end])


def grep(pattern, limit):
    out = []
    for i, ln in enumerate(GS.read_text(encoding="utf-8").splitlines(), 1):
        if re.search(pattern, ln):
            out.append(f"{i}:{ln}")
            if len(out) >= limit:
                break
    return "\n".join(out)


parts = {}
parts["step_map.txt"] = cli("--map-tokens", "2048", "--format", "json")
parts["step_detect1.txt"] = cli("--detect", "GenServer", "--format", "json",
                                "--max-results", "10")
parts["step_read_lines1_120.txt"] = read_range(1, 120)
parts["step_read_lines121_240.txt"] = read_range(121, 240)
parts["step_grep_callbacks.txt"] = grep(r"^\s*@(callback|optional_callback)", 20)
parts["step_read_lines571_690.txt"] = read_range(571, 690)
parts["step_read_lines691_810.txt"] = read_range(691, 810)
parts["step_read_lines811_870.txt"] = read_range(811, 870)
parts["step_grep_defcall.txt"] = grep(r"^\s*def call\(", 5)
parts["step_read_lines1166_1245.txt"] = read_range(1166, 1245)
parts["step_grep_startlink.txt"] = grep(r"^\s*def start_link", 5)
parts["step_read_lines1071_1130.txt"] = read_range(1071, 1130)
parts["step_grep_macro.txt"] = grep(r"defoverridable|defmacro.*use", 10)
parts["step_read_lines911_960.txt"] = read_range(911, 960)

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
