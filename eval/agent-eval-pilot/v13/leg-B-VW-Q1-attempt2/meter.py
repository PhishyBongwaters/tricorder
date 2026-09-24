#!/usr/bin/env python3
"""Meter B-VW-Q1 attempt 2 from the returned command list (15 steps)."""
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
            if re.search(pattern, ln, re.IGNORECASE):
                out.append(f"{p.relative_to(REPO).as_posix()}:{i}:{ln}")
                break
    return "\n".join(out)


def grep_file(rel, pattern):
    out = []
    for i, ln in enumerate(
            (REPO / rel).read_text(encoding="utf-8").splitlines(), 1):
        if re.search(pattern, ln):
            out.append(f"{i}:{ln}")
    return "\n".join(out)


def read_all(rel):
    return (REPO / rel).read_text(encoding="utf-8")


def read_range(rel, start, end):
    lines = (REPO / rel).read_text(encoding="utf-8").splitlines()
    return "\n".join(lines[start - 1:end])


parts = {}
parts["step01_ls_root.txt"] = listing(".")
parts["step02_grep_totp_src.txt"] = grep_rs("totp")
parts["step03_ls_src.txt"] = listing("src")
parts["step04_grep_totp_rs.txt"] = grep_rs("totp")
parts["step05_ls_api.txt"] = listing("src/api")
parts["step06_grep_modauth.txt"] = grep_rs("mod authenticator|use.*authenticator")
parts["step07_ls_core.txt"] = listing("src/api/core")
parts["step08_grep_validatetotp.txt"] = grep_rs("validate_totp")
parts["step09_ls_twofactor.txt"] = listing("src/api/core/two_factor")
parts["step10_read_coremod.txt"] = read_all("src/api/core/mod.rs")
parts["step11_read_auth.txt"] = read_all("src/api/core/two_factor/authenticator.rs")
parts["step12_read_tfmod.txt"] = read_all("src/api/core/two_factor/mod.rs")
parts["step13_read_ident810_909.txt"] = read_range("src/api/identity.rs", 810, 909)
parts["step14_read_tfmodels.txt"] = read_all("src/db/models/two_factor.rs")
parts["step15_grep_cargo.txt"] = grep_file("Cargo.toml", "totp")

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
