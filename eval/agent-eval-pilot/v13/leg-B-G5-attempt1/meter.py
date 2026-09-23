#!/usr/bin/env python3
"""Meter B-G5 attempt 1: reproduce baseline payloads, count tokens.

Reproduces each leg command's agent-visible output from disk (listings,
greps, reads) and counts with utils.count_tokens (tiktoken cl100k).
Formats mirror PowerShell Select-String (name:line:text) and dir listings
(sorted names) as in eval/agent-eval-pilot/meter_go.py — token-scale
equivalent to what the agent saw, not byte-identical.
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
        rel = p.relative_to(GO).as_posix()
        for i, ln in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            if re.search(pattern, ln):
                out.append(f"{p.name}:{i}:{ln}")
    return "\n".join(out)


def grep_recursive(subdir, pattern):
    out = []
    for p in sorted((GO / subdir).rglob("*.go")):
        try:
            lines = p.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        for i, ln in enumerate(lines, 1):
            if re.search(pattern, ln):
                out.append(f"{p.relative_to(GO).as_posix()}:{i}:{ln}")
    return "\n".join(out)


def read_range(rel, offset, limit):
    lines = (GO / rel).read_text(encoding="utf-8").splitlines()
    return "\n".join(lines[offset - 1:offset - 1 + limit])


def size_note(*rels):
    return "\n".join(f"{r}: {(GO / r).stat().st_size} bytes" for r in rels)


parts = {}
parts["step01_ls_root.txt"] = listing(".")
parts["step02_ls_src.txt"] = listing("src")
parts["step03_ls_cmd.txt"] = listing("src/cmd")
parts["step04_ls_compile.txt"] = listing("src/cmd/compile")
parts["step05_ls_internal.txt"] = listing("src/cmd/compile/internal")
parts["step06_ls_ssagen_ssa.txt"] = (
    listing("src/cmd/compile/internal/ssagen") + "\n---\n"
    + listing("src/cmd/compile/internal/ssa"))
parts["step07_grep_funcs.txt"] = grep_glob(
    "src/cmd/compile/internal/ssagen", "*.go",
    r"^func (Build|Compile|Gen|.*SSA)")
parts["step08_sizes_grep.txt"] = (
    size_note("src/cmd/compile/internal/ssagen/ssa.go",
              "src/cmd/compile/internal/ssagen/pgen.go")
    + "\n" + grep_files(["src/cmd/compile/internal/ssagen/ssa.go"],
                        r"buildssa|func BuildSSA|genssa"))
parts["step09_grep_pgen.txt"] = grep_files(
    ["src/cmd/compile/internal/ssagen/pgen.go"],
    r"^func |buildssa|Compile\(")
# second half of cmd 9 errored (bad -Include): delivered nothing.
parts["step10_grep_buildssa_recursive.txt"] = (
    grep_files(["src/cmd/compile/internal/ssagen/ssa.go"],
               r"func buildssa")
    + "\n" + grep_recursive("src/cmd/compile/internal",
                            r"ssagen\.Compile|buildssa\("))
parts["step11_read_pgen.txt"] = read_range(
    "src/cmd/compile/internal/ssagen/pgen.go", 295, 60)
parts["step12_read_ssa_head.txt"] = read_range(
    "src/cmd/compile/internal/ssagen/ssa.go", 298, 65)
parts["step13_read_driver.txt"] = read_range(
    "src/cmd/compile/internal/gc/compile.go", 160, 30)
parts["step14_read_ssa_setup.txt"] = read_range(
    "src/cmd/compile/internal/ssagen/ssa.go", 362, 80)
parts["step15_grep_lowering.txt"] = grep_files(
    ["src/cmd/compile/internal/ssagen/ssa.go"],
    r"ssa\.Compile|compiler\.Compile|\.stmt\(|\.stmtList|finishFunc|Free IR")
parts["step16_read_ssa_tail.txt"] = read_range(
    "src/cmd/compile/internal/ssagen/ssa.go", 575, 50)

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
