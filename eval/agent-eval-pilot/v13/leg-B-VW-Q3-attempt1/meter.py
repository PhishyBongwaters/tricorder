#!/usr/bin/env python3
"""Meter B-VW-Q3 attempt 1."""
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


ORGS = "src/api/core/organizations.rs"
COLL = "src/db/models/collection.rs"
CIPHER = "src/db/models/cipher.rs"
ORG = "src/db/models/organization.rs"

parts = {}
parts["step01_ls_root.txt"] = listing(".")
parts["step02_grep_orgcoll.txt"] = grep_recursive(
    r"organization.*collection|collection.*access|collection_permissions", re.IGNORECASE)
parts["step03_grep_accessall.txt"] = grep_recursive(
    r"access_all|collection_access|check_collection_access", re.IGNORECASE)
parts["step04_read_orgs.txt"] = read_range(ORGS, 490, 250)
parts["step05_grep_core.txt"] = grep_recursive(
    r"is_manageable_by_user|access_all|check_access")
parts["step06_read_coll.txt"] = read_range(COLL, 565, 70)
parts["step07_read_cipher.txt"] = read_range(CIPHER, 620, 100)
parts["step08_read_org.txt"] = read_range(ORG, 50, 100)

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