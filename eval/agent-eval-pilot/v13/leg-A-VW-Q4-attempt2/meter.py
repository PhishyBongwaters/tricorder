#!/usr/bin/env python3
"""Meter A-VW-Q4 attempt 2 from the recalled command list (11 steps)."""
import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))
from utils import count_tokens

PY = r"D:\Projects\tricorder\.venv\Scripts\python.exe"
CLI = str(Path(__file__).resolve().parents[4] / "tricorder.py")
ROOT = r"D:\Projects\Tricorder-Testing-Repos\vaultwarden"
OUT = Path(__file__).resolve().parent


def run_cli(*args):
    p = subprocess.run([PY, CLI, "--root", ROOT, *args],
                       capture_output=True, text=True, encoding="utf-8")
    return p.stdout


def read_range(rel, start, end):
    lines = (Path(ROOT) / rel).read_text(encoding="utf-8").splitlines()
    return "\n".join(lines[start - 1:end])


parts = {}
parts["step_smartmap.txt"] = run_cli("--smart-map", "send_cipher_update",
                                     "--format", "json", "--max-results", "5")
parts["step_detect.txt"] = run_cli("--detect", "send_cipher_update",
                                   "--format", "json", "--max-results", "5")
parts["step_symbols.txt"] = run_cli("--symbols", "send_cipher_update",
                                    "--format", "json")
parts["step_read_notif_430_477.txt"] = read_range(
    "src/api/notifications.rs", 430, 477)
parts["step_read_ciphers_556_585.txt"] = read_range(
    "src/api/core/ciphers.rs", 556, 585)
parts["step_read_ciphers_831_855.txt"] = read_range(
    "src/api/core/ciphers.rs", 831, 855)
parts["step_read_ciphers_911_935.txt"] = read_range(
    "src/api/core/ciphers.rs", 911, 935)
parts["step_read_notif_2_51.txt"] = read_range("src/api/notifications.rs", 2, 51)
parts["step_read_notif_354_373.txt"] = read_range("src/api/notifications.rs", 354, 373)
parts["step_read_notif_627_656.txt"] = read_range("src/api/notifications.rs", 627, 656)
parts["step_read_push_160_189.txt"] = read_range("src/api/push.rs", 160, 189)

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