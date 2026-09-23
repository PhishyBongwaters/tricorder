#!/usr/bin/env python3
"""Meter B-VW-Q2 attempt 1: reproduce baseline payloads, count tokens."""
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))
from utils import count_tokens

VW = Path(r"D:\Projects\Tricorder-Testing-Repos\vaultwarden")
OUT = Path(__file__).resolve().parent


def listing(rel):
    return "\n".join(sorted(p.name for p in (VW / rel).iterdir()))


def read_range(rel, offset, limit):
    lines = (VW / rel).read_text(encoding="utf-8").splitlines()
    return "\n".join(lines[offset - 1:offset - 1 + limit])


ADMIN = "src/api/admin.rs"
AUTH = "src/auth.rs"
parts = {}
parts["step01_ls_root.txt"] = listing(".")
parts["step02_ls_src.txt"] = listing("src")
parts["step03_ls_api.txt"] = listing("src/api")
parts["step04_read_admin.txt"] = read_range(ADMIN, 1, 927)
parts["step05_read_auth.txt"] = read_range(AUTH, 1, 1341)

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