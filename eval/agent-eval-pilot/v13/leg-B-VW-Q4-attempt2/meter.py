#!/usr/bin/env python3
"""Meter B-VW-Q4 attempt 2 from the returned command list (15 steps)."""
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


def read_all(rel):
    return (REPO / rel).read_text(encoding="utf-8")


def read_range(rel, start, end):
    lines = (REPO / rel).read_text(encoding="utf-8").splitlines()
    return "\n".join(lines[start - 1:end])


parts = {}
parts["step01_ls_root.txt"] = listing(".")
parts["step02_grep_notif.txt"] = grep_rs("notification")
parts["step03_grep_cipher_notif.txt"] = grep_rs("cipher.*notif|notif.*cipher|push_notification|notify_cipher|cipher_changed")
parts["step04_grep_websocket_push.txt"] = grep_rs("live.*notif|websocket|signal|push.*send|send_push|notification")
parts["step05_grep_push_cipher.txt"] = grep_rs("push_cipher_update|cipher_update|cipher.*update")
parts["step06_grep_send_notif.txt"] = grep_rs("send_notification|notify_user|notify_device|send_push")
parts["step07_grep_send_cipher.txt"] = grep_rs("send_cipher_update|\.notify\.")
parts["step08_grep_cipher_save.txt"] = grep_rs("cipher.*save|save.*cipher|put_cipher|post_cipher|patch_cipher")
parts["step09_ls_src.txt"] = listing("src")
parts["step10_grep_notify_ciphers.txt"] = grep_rs("notify|send_cipher_update|Notify")
parts["step11_read_notif.txt"] = read_all("src/api/notifications.rs")
parts["step12_read_push.txt"] = read_all("src/api/push.rs")
parts["step13_read_ciphers_395_578.txt"] = read_range("src/api/core/ciphers.rs", 395, 578)
parts["step14_read_ciphers_820_944.txt"] = read_range("src/api/core/ciphers.rs", 820, 944)
parts["step15_read_ciphers_1770_1869.txt"] = read_range("src/api/core/ciphers.rs", 1770, 1869)

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