#!/usr/bin/env python3
"""Meter A-Elixir-Q1 attempt 3 from the recalled command list (12 steps)."""
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
parts["step_map.txt"] = cli("--format", "json", "--map-tokens", "2048")
parts["step_detect1.txt"] = cli("--detect", "GenServer", "--format", "json",
                                "--max-results", "10")
parts["step_read_1_120.txt"] = read_range(1, 120)
parts["step_read_121_240.txt"] = read_range(121, 240)
parts["step_grep_callback.txt"] = grep(r"@callback", 20)
parts["step_read_577_699.txt"] = read_range(577, 699)
parts["step_read_700_849.txt"] = read_range(700, 849)
parts["step_read_1166_1230.txt"] = read_range(1166, 1230)
parts["step_read_1071_1110.txt"] = read_range(1071, 1110)
parts["step_read_1241_1260.txt"] = read_range(1241, 1260)
parts["step_grep_macro.txt"] = grep(
    r"defmacro use GenServer|defoverridable|@behaviour", 10)
parts["step_read_891_1025.txt"] = read_range(891, 1025)

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
