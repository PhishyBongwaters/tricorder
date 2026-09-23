#!/usr/bin/env python3
"""Meter B-VW-Q1 attempt 1: reproduce baseline payloads, count tokens.

Same conventions as the Go B-leg meters. Cmd 2 (bare grep on PowerShell)
errored and delivered nothing: no artifact, counted 0.
"""
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


def grep_files(files, pattern, flags=0):
    out = []
    for rel in files:
        for i, ln in enumerate((VW / rel).read_text(encoding="utf-8").splitlines(), 1):
            if re.search(pattern, ln, flags):
                out.append(f"{Path(rel).name}:{i}:{ln}")
    return "\n".join(out)


def grep_recursive(pattern, flags=0):
    out = []
    for p in sorted((VW / "src").rglob("*.rs")):
        try:
            lines = p.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        for i, ln in enumerate(lines, 1):
            if re.search(pattern, ln, flags):
                out.append(f"{p.relative_to(VW).as_posix()}:{i}:{ln}")
    return "\n".join(out)


def read_range(rel, offset, limit):
    lines = (VW / rel).read_text(encoding="utf-8").splitlines()
    return "\n".join(lines[offset - 1:offset - 1 + limit])


def size_note(*rels):
    chunks = []
    for r in rels:
        p = VW / r
        n = len(p.read_text(encoding="utf-8").splitlines())
        chunks.append(f"{r}: {p.stat().st_size} bytes / {n} lines")
    return "\n".join(chunks)


AUTH = "src/api/core/two_factor/authenticator.rs"
IDENT = "src/api/identity.rs"
parts = {}
parts["step01_ls_root.txt"] = listing(".")
parts["step03_grep_totp.txt"] = grep_recursive(r"totp", re.IGNORECASE)
parts["step04_grep_authmod.txt"] = grep_recursive(
    r"mod authenticator|fn validate_totp|validate.*authenticator")
parts["step05_grep_twofactor.txt"] = grep_recursive(
    r"TwoFactor|two_factor|twofactor")
parts["step06_grep_ls_module.txt"] = (
    grep_recursive(r"mod authenticator|fn validate_totp")
    + "\n---\n" + listing("src/api/core/two_factor"))
parts["step07_sizes.txt"] = size_note(AUTH)
parts["step08_read_auth_full.txt"] = read_range(AUTH, 1, 182)
parts["step09_size_identity.txt"] = size_note(IDENT)
parts["step10_read_caller.txt"] = read_range(IDENT, 815, 40)
parts["step11_read_imports.txt"] = read_range(IDENT, 15, 20)

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
