#!/usr/bin/env python3
"""Meter B-G3 attempt 1: reproduce baseline payloads, count tokens.

Same conventions as the B-G5/B-G1 meters. Cmd 2 (bare grep/wc on
PowerShell) errored and delivered nothing: no artifact, counted 0.
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


def read_range(rel, offset, limit):
    lines = (GO / rel).read_text(encoding="utf-8").splitlines()
    return "\n".join(lines[offset - 1:offset - 1 + limit])


CHAN = "src/runtime/chan.go"
parts = {}
parts["step01_ls_runtime.txt"] = listing("src/runtime")
n = len((GO / CHAN).read_text(encoding="utf-8").splitlines())
parts["step03_count_grep.txt"] = (
    f"{CHAN}: {n} lines\n" + grep_files(
        [CHAN], r"^func (chansend|chanrecv|makechan|closechan|chanlen|chancap)"))
parts["step04_read_send.txt"] = read_range(CHAN, 155, 60)
parts["step05_read_recv.txt"] = read_range(CHAN, 495, 70)
parts["step06_grep_struct.txt"] = grep_files(
    [CHAN], r"type hchan struct|^func selectnbsend|^func selectnbrecv")
parts["step07_read_struct.txt"] = read_range(CHAN, 34, 20)
parts["step08_read_wrappers.txt"] = read_range(CHAN, 776, 50)

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
