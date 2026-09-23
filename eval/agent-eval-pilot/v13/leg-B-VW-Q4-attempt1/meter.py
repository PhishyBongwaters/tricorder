#!/usr/bin/env python3
"""Meter B-VW-Q4 attempt 1."""
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


NOTIF = "src/api/notifications.rs"
CIPHERS = "src/api/core/ciphers.rs"
PUSH = "src/api/push.rs"

parts = {}
parts["step01_ls_root.txt"] = listing(".")
parts["step02_ls_src.txt"] = listing("src")
parts["step03_ls_api.txt"] = listing("src/api")
parts["step04_ls_core.txt"] = listing("src/api/core")
parts["step05_read_notif.txt"] = read_range(NOTIF, 1, 700)
parts["step06_grep_send.txt"] = ""
# Read ciphers sections that call send_cipher_update
parts["step07_read_create.txt"] = read_range(CIPHERS, 320, 80)
parts["step08_read_update.txt"] = read_range(CIPHERS, 500, 80)
parts["step09_read_coll.txt"] = read_range(CIPHERS, 820, 60)
parts["step10_read_admin.txt"] = read_range(CIPHERS, 895, 80)
parts["step11_read_attach.txt"] = read_range(CIPHERS, 1310, 50)
parts["step12_read_move.txt"] = read_range(CIPHERS, 1620, 50)
parts["step13_read_delete.txt"] = read_range(CIPHERS, 1775, 80)
parts["step14_read_restore.txt"] = read_range(CIPHERS, 1875, 60)
parts["step15_read_attachdel.txt"] = read_range(CIPHERS, 1955, 60)
parts["step16_read_archive.txt"] = read_range(CIPHERS, 2000, 70)
parts["step17_read_push.txt"] = read_range(PUSH, 1, 200)

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