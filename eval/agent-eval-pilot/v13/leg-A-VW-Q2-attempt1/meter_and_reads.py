#!/usr/bin/env python3
"""Capture A-VW-Q2 reads and meter the leg."""
import os
from pathlib import Path

ROOT = Path(r"D:\Projects\Tricorder-Testing-Repos\vaultwarden")
OUT = Path(__file__).resolve().parent

def read_range(rel, start, end):
    p = ROOT / rel
    lines = p.read_text(encoding="utf-8").splitlines()
    return "\n".join(f"{i+1}: {lines[i]}" for i in range(start, min(end, len(lines))))

reads = {
    "step_read_admin_guard.txt": read_range("src/api/admin.rs", 856, 927),
    "step_read_login.txt": read_range("src/api/admin.rs", 149, 229),
    "step_read_validate.txt": read_range("src/api/admin.rs", 228, 304),
    "step_read_decode.txt": read_range("src/auth.rs", 144, 204),
    "step_read_claims.txt": read_range("src/auth.rs", 524, 564),
    "step_read_encode.txt": read_range("src/auth.rs", 104, 154),
    "step_read_issuer.txt": read_range("src/auth.rs", 55, 65),
}

for name, text in reads.items():
    (OUT / name).write_text(text, encoding="utf-8")

# Now meter
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))
from utils import count_tokens

total = 0
for p in sorted(OUT.glob("step_*.txt")):
    raw = p.read_bytes()
    text = raw.decode("utf-16") if b"\x00" in raw[:64] else raw.decode("utf-8", errors="replace")
    tk = count_tokens(text)
    total += tk
    print(f"{p.name}: {tk} tokens")
print(f"TOTAL: {total} tokens")