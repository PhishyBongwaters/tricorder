#!/usr/bin/env python3
"""Meter A-VW-Q2 attempt 3: 19 enumerated ops claimed as 15 (overrun kept)."""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))
from utils import count_tokens

PY = r"D:\Projects\tricorder\.venv\Scripts\python.exe"
CLI = str(Path(__file__).resolve().parents[4] / "tricorder.py")
ROOT = r"D:\Projects\Tricorder-Testing-Repos\vaultwarden"
ADM = Path(ROOT) / "src" / "api" / "admin.rs"
AUT = Path(ROOT) / "src" / "auth.rs"
OUT = Path(__file__).resolve().parent


def cli(*args):
    p = subprocess.run([PY, CLI, "--root", ROOT, *args],
                       capture_output=True, text=True, encoding="utf-8")
    return p.stdout


def read_range(path, start, end):
    lines = path.read_text(encoding="utf-8").splitlines()
    return "\n".join(lines[start - 1:end])


def grep_file(path, pattern, limit=10):
    out = []
    for i, ln in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if re.search(pattern, ln):
            out.append(f"{i}:{ln}")
            if len(out) >= limit:
                break
    return "\n".join(out)


parts = {}
parts["step_probe.txt"] = cli("--probe-digest")
parts["step_detect_admin.txt"] = cli("--detect", "admin", "--format", "json",
                                     "--max-results", "5")
parts["step_symbols_admin.txt"] = cli("--symbols", "admin", "--format", "json",
                                      "--max-results", "5")
parts["step_tier1.txt"] = cli("--tier", "1", "--context-lines", "3",
                              "--format", "json")
parts["step_symbols_admintoken.txt"] = cli("--symbols", "AdminToken",
                                           "--format", "json",
                                           "--max-results", "5")
parts["step_symbols_fromrequest.txt"] = cli("--symbols", "AdminToken::from_request",
                                            "--format", "json",
                                            "--max-results", "5")
parts["step_read_adm1_50.txt"] = read_range(ADM, 1, 50)
parts["step_read_adm51_110.txt"] = read_range(ADM, 51, 110)
parts["step_read_adm111_210.txt"] = read_range(ADM, 111, 210)
parts["step_read_adm211_310.txt"] = read_range(ADM, 211, 310)
parts["step_read_adm850_909.txt"] = read_range(ADM, 850, 909)
parts["step_read_auth810_839.txt"] = read_range(AUT, 810, 839)
parts["step_read_auth155_184.txt"] = read_range(AUT, 155, 184)
parts["step_read_auth105_124.txt"] = read_range(AUT, 105, 124)
parts["step_read_auth528_547.txt"] = read_range(AUT, 528, 547)
parts["step_grep_decodeadmin.txt"] = grep_file(ADM, r"fn decode_admin")
parts["step_grep_jwtfns.txt"] = grep_file(
    ADM, r"fn (encode_jwt|generate_admin_claims)")
parts["step_grep_issuer.txt"] = grep_file(AUT, r"JWT_ADMIN_ISSUER")
parts["step_grep_admintoken_cfg.txt"] = grep_file(
    Path(ROOT) / "src" / "config.rs", r"admin_token")

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
