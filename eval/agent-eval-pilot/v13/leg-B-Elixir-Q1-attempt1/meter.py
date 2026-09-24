#!/usr/bin/env python3
"""Meter B-Elixir-Q1 attempt 1 from the returned command list (15 steps)."""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))
from utils import count_tokens

REPO = Path(r"D:\Projects\Tricorder-Testing-Repos\elixir")
GS = REPO / "lib" / "elixir" / "lib" / "gen_server.ex"
BEH = REPO / "lib" / "elixir" / "lib" / "behaviour.ex"
OUT = Path(__file__).resolve().parent


def listing(rel):
    return "\n".join(sorted(p.name for p in (REPO / rel).iterdir()))


def read_range(path, start, end):
    lines = path.read_text(encoding="utf-8").splitlines()
    return "\n".join(lines[start - 1:end])


def measure(path):
    return str(sum(1 for _ in path.read_text(encoding="utf-8").splitlines()))


parts = {}
parts["step01_ls_root.txt"] = listing(".")
parts["step02_ls_lib.txt"] = listing("lib")
parts["step03_ls_elixir_lib.txt"] = listing("lib/elixir/lib")
parts["step04_measure_gs.txt"] = measure(GS)
parts["step05_read_1_200.txt"] = read_range(GS, 1, 200)
parts["step06_read_201_400.txt"] = read_range(GS, 201, 400)
parts["step07_read_401_600.txt"] = read_range(GS, 401, 600)
parts["step08_read_601_800.txt"] = read_range(GS, 601, 800)
parts["step09_read_801_1000.txt"] = read_range(GS, 801, 1000)
parts["step10_read_1001_1100.txt"] = read_range(GS, 1001, 1100)
parts["step11_read_1101_1200.txt"] = read_range(GS, 1101, 1200)
parts["step12_read_1201_1300.txt"] = read_range(GS, 1201, 1300)
parts["step13_read_1301_1376.txt"] = read_range(GS, 1301, 1376)
parts["step14_measure_beh.txt"] = measure(BEH)
parts["step15_read_beh.txt"] = read_range(BEH, 1, 128)

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
