#!/usr/bin/env python3
"""Meter B-VW-Q2 attempt 2 from the returned command list (6 steps)."""
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))
from utils import count_tokens

REPO = Path(r"D:\Projects\Tricorder-Testing-Repos\vaultwarden")
OUT = Path(__file__).resolve().parent


def listing(rel):
    return "\n".join(sorted(p.name for p in (REPO / rel).iterdir()))


def grep_rs(pattern):
    out = []
    for p in sorted((REPO / "src").rglob("*.rs")):
        try:
            lines = p.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        for i, ln in enumerate(lines, 1):
            if re.search(pattern, ln):
                out.append(f"{p.relative_to(REPO).as_posix()}:{i}:{ln}")
                break
    return "\n".join(out)


def grep_file(rel, pattern):
    out = []
    for i, ln in enumerate(
            (REPO / rel).read_text(encoding="utf-8").splitlines(), 1):
        if re.search(pattern, ln, re.IGNORECASE):
            out.append(f"{i}:{ln}")
    return "\n".join(out)


parts = {}
parts["step01_ls_root.txt"] = listing(".")
parts["step02_ls_src.txt"] = listing("src")
parts["step03_grep_admin.txt"] = grep_rs("admin")
parts["step04_read_admin.txt"] = (REPO / "src/api/admin.rs").read_text(encoding="utf-8")
parts["step05_read_auth.txt"] = (REPO / "src/auth.rs").read_text(encoding="utf-8")
parts["step06_grep_config.txt"] = grep_file(
    "src/config.rs", "admin_token|admin_session_lifetime|disable_admin_token|is_admin_token_set")

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
