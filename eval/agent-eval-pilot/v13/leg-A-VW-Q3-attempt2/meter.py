#!/usr/bin/env python3
"""Meter A-VW-Q3 attempt 2 from the recalled command list (15 CLI + 12 reads)."""
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
parts["step_probe.txt"] = run_cli("--probe-digest")
parts["step_detect_collection_access.txt"] = run_cli("--detect", "collection_access",
                                                     "--format", "json", "--max-results", "5")
parts["step_detect_is_collection_user.txt"] = run_cli("--detect", "is_collection_user",
                                                      "--format", "json", "--max-results", "5")
parts["step_detect_has_collection_perm.txt"] = run_cli("--detect", "has_collection_permission",
                                                       "--format", "json", "--max-results", "5")
parts["step_detect_has_manageable.txt"] = run_cli("--detect", "has_manageable_collection_by_user",
                                                  "--format", "json", "--max-results", "5")
parts["step_detect_is_coll_manageable.txt"] = run_cli("--detect", "is_coll_manageable_by_user",
                                                      "--format", "json", "--max-results", "5")
parts["step_detect_has_access_by_user.txt"] = run_cli("--detect", "has_access_to_collection_by_user",
                                                      "--format", "json", "--max-results", "5")
parts["step_symbols_is_coll_manageable.txt"] = run_cli("--symbols", "is_coll_manageable_by_user",
                                                       "--format", "json", "--max-results", "5")
parts["step_symbols_has_access_by_user.txt"] = run_cli("--symbols", "has_access_to_collection_by_user",
                                                       "--format", "json", "--max-results", "5")
parts["step_tier1_is_coll_manageable.txt"] = run_cli("--tier", "1", "--context-lines", "3",
                                                     "--symbols", "is_coll_manageable_by_user",
                                                     "--format", "json", "--max-results", "5")
parts["step_symbols_find_by_coll_user.txt"] = run_cli("--symbols", "find_by_collection_and_user",
                                                      "--format", "json", "--max-results", "5")
parts["step_symbols_has_access_by_member.txt"] = run_cli("--symbols", "has_access_to_collection_by_member",
                                                         "--format", "json", "--max-results", "5")
parts["step_symbols_has_full_access_by_member.txt"] = run_cli("--symbols", "has_full_access_by_member",
                                                              "--format", "json", "--max-results", "5")
parts["step_symbols_has_full_access.txt"] = run_cli("--symbols", "has_full_access",
                                                    "--format", "json", "--max-results", "5")
parts["step_symbols_get_access_restrictions.txt"] = run_cli("--symbols", "get_access_restrictions",
                                                            "--format", "json", "--max-results", "5")
# Shell reads
parts["step_read_collection_570_629.txt"] = read_range(
    "src/db/models/collection.rs", 570, 629)
parts["step_read_collection_635_673.txt"] = read_range(
    "src/db/models/collection.rs", 635, 673)
parts["step_read_collection_901_907.txt"] = read_range(
    "src/db/models/collection.rs", 901, 907)
parts["step_read_collection_837_853.txt"] = read_range(
    "src/db/models/collection.rs", 837, 853)
parts["step_read_auth_884_901.txt"] = read_range("src/auth.rs", 884, 901)
parts["step_read_auth_966_980.txt"] = read_range("src/auth.rs", 966, 980)
parts["step_read_orgs_431_470.txt"] = read_range("src/api/core/organizations.rs", 431, 470)
parts["step_read_group_571_594.txt"] = read_range("src/db/models/group.rs", 571, 594)
parts["step_read_group_595_614.txt"] = read_range("src/db/models/group.rs", 595, 614)
parts["step_read_org_831_835.txt"] = read_range("src/db/models/organization.rs", 831, 835)
parts["step_read_cipher_721_738.txt"] = read_range("src/db/models/cipher.rs", 721, 738)
parts["step_read_cipher_597_668.txt"] = read_range("src/db/models/cipher.rs", 597, 668)

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