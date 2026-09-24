#!/usr/bin/env python3
"""Meter A-Elixir-Q1 attempt 4 from the returned command list (15 steps)."""
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
parts["step_probe.txt"] = cli("--probe-digest")
parts["step_detect_genserver.txt"] = cli("--detect", "GenServer",
                                         "--format", "json",
                                         "--max-results", "5")
parts["step_detect_callback.txt"] = cli("--detect", "callback",
                                        "--format", "json",
                                        "--max-results", "5")
parts["step_detect_init.txt"] = cli("--detect", "init", "--format", "json",
                                    "--max-results", "5")
parts["step_symbols_genserver.txt"] = cli("--symbols", "GenServer",
                                          "--format", "json",
                                          "--max-results", "5")
parts["step_detect_handlecall.txt"] = cli("--detect", "handle_call",
                                          "--format", "json",
                                          "--max-results", "5")
parts["step_detect_handlecast.txt"] = cli("--detect", "handle_cast",
                                          "--format", "json",
                                          "--max-results", "5")
parts["step_read_1_120.txt"] = read_range(1, 120)
parts["step_read_121_240.txt"] = read_range(121, 240)
parts["step_read_241_360.txt"] = read_range(241, 360)
parts["step_read_361_480.txt"] = read_range(361, 480)
parts["step_read_481_600.txt"] = read_range(481, 600)
parts["step_read_601_720.txt"] = read_range(601, 720)
parts["step_read_721_840.txt"] = read_range(721, 840)
parts["step_read_841_960.txt"] = read_range(841, 960)

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
