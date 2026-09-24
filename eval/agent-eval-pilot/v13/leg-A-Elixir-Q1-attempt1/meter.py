#!/usr/bin/env python3
"""Meter A-Elixir-Q1 attempt 1 from the recalled command list (9 steps)."""
import json
import os
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


parts = {}
parts["step_map.txt"] = cli("--map-tokens", "2048", "--format", "json")
parts["step_detect1.txt"] = cli("--detect", "GenServer", "--format", "json",
                                "--max-results", "10")
parts["step_symbols1.txt"] = cli("--symbols", "GenServer", "--format", "json")
parts["step_detect2.txt"] = cli("--detect", "callback", "--format", "json",
                                "--max-results", "10")
parts["step_read_lines1_200.txt"] = read_range(1, 200)
parts["step_read_lines201_500.txt"] = read_range(201, 500)
parts["step_read_lines501_800.txt"] = read_range(501, 800)
parts["step_read_lines801_1100.txt"] = read_range(801, 1100)
parts["step_read_lines1101_1376.txt"] = read_range(1101, 1376)

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
