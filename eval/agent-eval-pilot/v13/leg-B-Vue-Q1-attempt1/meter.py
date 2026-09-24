#!/usr/bin/env python3
"""Meter B-Vue-Q1 attempt 1 from the returned command list (15 steps)."""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))
from utils import count_tokens

REPO = Path(r"D:\Projects\Tricorder-Testing-Repos\vue")
OB = REPO / "src" / "core" / "observer"
OUT = Path(__file__).resolve().parent


def listing(rel):
    return "\n".join(sorted(p.name for p in (REPO / rel).iterdir()))


def read_all(path):
    return path.read_text(encoding="utf-8")


parts = {}
parts["step01_ls_root.txt"] = listing(".")
parts["step02_ls_packages.txt"] = listing("packages")
parts["step03_ls_tmplcomp.txt"] = listing("packages/template-compiler")
parts["step04_ls_src.txt"] = listing("src")
parts["step05_ls_core.txt"] = listing("src/core")
parts["step06_ls_v3.txt"] = listing("src/v3")
parts["step07_ls_observer.txt"] = listing("src/core/observer")
parts["step08_ls_v3react.txt"] = listing("src/v3/reactivity")
parts["step09_ls_v3_again.txt"] = listing("src/v3")
parts["step10_read_index.txt"] = read_all(OB / "index.ts")
parts["step11_read_dep.txt"] = read_all(OB / "dep.ts")
parts["step12_read_watcher.txt"] = read_all(OB / "watcher.ts")
parts["step13_read_sched.txt"] = read_all(OB / "scheduler.ts")
parts["step14_read_ref.txt"] = read_all(REPO / "src/v3/reactivity/ref.ts")
parts["step15_read_reactive.txt"] = read_all(REPO / "src/v3/reactivity/reactive.ts")

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
