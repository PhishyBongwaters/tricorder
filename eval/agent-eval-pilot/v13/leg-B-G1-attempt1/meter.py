#!/usr/bin/env python3
"""Meter B-G1 attempt 1: reproduce baseline payloads, count tokens.

Same conventions as ../leg-B-G5-attempt1/meter.py: listings, greps and
reads reproduced from disk; formats mirror PowerShell Select-String
(name:line:text). Cmd 2 (bare `grep` on PowerShell) errored and delivered
nothing: no artifact, counted 0.
"""
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))
from utils import count_tokens

GO = Path(r"D:\Projects\Tricorder-Testing-Repos\go")
OUT = Path(__file__).resolve().parent


def listing(rel):
    return "\n".join(sorted(p.name for p in (GO / rel).iterdir()))


def grep_files(files, pattern):
    out = []
    for rel in files:
        for i, ln in enumerate((GO / rel).read_text(encoding="utf-8").splitlines(), 1):
            if re.search(pattern, ln):
                out.append(f"{Path(rel).name}:{i}:{ln}")
    return "\n".join(out)


def grep_glob(subdir, glob, pattern):
    out = []
    for p in sorted((GO / subdir).glob(glob)):
        for i, ln in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            if re.search(pattern, ln):
                out.append(f"{p.name}:{i}:{ln}")
    return "\n".join(out)


def read_range(rel, offset, limit):
    lines = (GO / rel).read_text(encoding="utf-8").splitlines()
    return "\n".join(lines[offset - 1:offset - 1 + limit])


def size_note(*rels):
    chunks = []
    for r in rels:
        p = GO / r
        n = len(p.read_text(encoding="utf-8").splitlines())
        chunks.append(f"{r}: {p.stat().st_size}B/{n} lines")
    return "\n".join(chunks)


parts = {}
parts["step01_ls_runtime.txt"] = listing("src/runtime")
parts["step03_grep_worker.txt"] = grep_glob(
    "src/runtime", "*.go", r"gcBgMarkWorker")
parts["step04_sizes.txt"] = size_note("src/runtime/mgc.go",
                                      "src/runtime/mgcmark.go")
parts["step05_read_worker.txt"] = read_range(
    "src/runtime/mgc.go", 1660, 240)
parts["step06_read_tail_head.txt"] = (
    read_range("src/runtime/mgc.go", 1900, 60)
    + "\n" + read_range("src/runtime/mgcmark.go", 1, 120))
parts["step07_grep_mark_funcs.txt"] = grep_files(
    ["src/runtime/mgcmark.go"],
    r"^func gc.*Mark|^func gcDrain|^func markroot")
parts["step08_grep_orchestration.txt"] = grep_files(
    ["src/runtime/mgc.go"],
    r"^func gcMark|^func gcDrain|^func gcBgMark")
parts["step09_read_cores.txt"] = (
    read_range("src/runtime/mgc.go", 1972, 114)
    + "\n" + read_range("src/runtime/mgcmark.go", 1253, 170))
parts["step10_read_done_wrappers.txt"] = (
    read_range("src/runtime/mgc.go", 997, 105)
    + "\n" + read_range("src/runtime/mgcmark.go", 1181, 75))

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
