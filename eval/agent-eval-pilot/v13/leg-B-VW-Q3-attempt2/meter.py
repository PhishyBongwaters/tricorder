#!/usr/bin/env python3
"""Meter B-VW-Q3 attempt 2 from the returned command list (33 steps, over cap)."""
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
parts["step02_grep_collection.txt"] = grep_rs("collection")
parts["step03_grep_perm.txt"] = grep_rs("collection.*permission|permission.*collection")
parts["step04_grep_access.txt"] = grep_rs("collection.*access|access.*collection")
parts["step05_ls_src.txt"] = listing("src")
parts["step06_ls_models.txt"] = listing("src/db/models")
parts["step07_grep_can_access.txt"] = grep_rs("can_access_collection")
parts["step08_grep_coll_uuid.txt"] = grep_rs("collection_uuid")
parts["step09_ls_api_core.txt"] = listing("src/api/core")
parts["step10_grep_coll_ciphers.txt"] = grep_rs("collection")
parts["step11_read_collection.txt"] = read_all("src/db/models/collection.rs")
parts["step12_grep_org.txt"] = grep_rs("is_writable_by_user|is_coll_manageable|is_manageable_by_user|is_admin|AdminHeaders")
parts["step13_read_orgs_1830_1979.txt"] = read_range("src/api/core/organizations.rs", 1830, 1979)
parts["step14_grep_cipher_funcs.txt"] = grep_rs("is_in_editable_collection|is_write_accessible|get_collections|get_admin_collections")
parts["step15_read_cipher_710_769.txt"] = read_range("src/db/models/cipher.rs", 710, 769)
parts["step16_grep_get_access.txt"] = grep_rs("get_access_restrictions")
parts["step17_read_cipher_597_716.txt"] = read_range("src/db/models/cipher.rs", 597, 716)
parts["step18_read_cipher_971_1050.txt"] = read_range("src/db/models/cipher.rs", 971, 1050)
parts["step19_read_ciphers_797_956.txt"] = read_range("src/api/core/ciphers.rs", 797, 956)
parts["step20_read_ciphers_955_1086.txt"] = read_range("src/api/core/ciphers.rs", 955, 1086)
parts["step20b_grep_shortcuts.txt"] = grep_rs("is_owned_by_user|is_in_full_access_org|is_in_full_access_group")
parts["step21_read_cipher_550_599.txt"] = read_range("src/db/models/cipher.rs", 550, 599)
parts["step22_grep_group.txt"] = grep_rs("has_full_access_by_member|has_access_to_collection")
parts["step23_read_group_565_624.txt"] = read_range("src/db/models/group.rs", 565, 624)
parts["step24_grep_org_full.txt"] = grep_rs("has_full_access")
parts["step25_read_org_75_154.txt"] = read_range("src/db/models/organization.rs", 75, 154)
parts["step26_grep_org_full2.txt"] = grep_rs("has_full_access")
parts["step27_read_org_828_857.txt"] = read_range("src/db/models/organization.rs", 828, 857)
parts["step28_grep_cipher_writable.txt"] = grep_rs("is_writable_by_user")
parts["step29_read_orgs_580_619.txt"] = read_range("src/api/core/organizations.rs", 580, 619)
parts["step30_grep_cipher_accessible.txt"] = grep_rs("is_accessible_to_user")
parts["step31_read_cipher_147_226.txt"] = read_range("src/db/models/cipher.rs", 147, 226)
parts["step32_grep_coll_manage.txt"] = grep_rs("is_manageable")
parts["step33_grep_schema.txt"] = grep_rs("collection")

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