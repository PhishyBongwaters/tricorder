#!/usr/bin/env python3
"""Meter A-Rails-Q1 attempt 2 from the recalled command list (10 CLI + 12 reads)."""
import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))
from utils import count_tokens

PY = r"D:\Projects\tricorder\.venv\Scripts\python.exe"
CLI = str(Path(__file__).resolve().parents[4] / "tricorder.py")
ROOT = r"D:\Projects\Tricorder-Testing-Repos\rails"
OUT = Path(__file__).resolve().parent


def run_cli(*args):
    p = subprocess.run([PY, CLI, "--root", ROOT, *args],
                       capture_output=True, text=True, encoding="utf-8")
    return p.stdout


def read_range(rel, start, end):
    lines = (Path(ROOT) / rel).read_text(encoding="utf-8").splitlines()
    return "\n".join(lines[start - 1:end])


parts = {}
# CLI calls
parts["step_smartmap.txt"] = run_cli("--smart-map", "has_many",
                                     "--format", "json", "--max-results", "5")
parts["step_detect_has_many.txt"] = run_cli("--detect", "has_many",
                                            "--format", "json", "--max-results", "5")
parts["step_symbols_has_many.txt"] = run_cli("--symbols", "has_many",
                                             "--format", "json")
parts["step_detect_builder_hasmany.txt"] = run_cli("--detect", "Builder::HasMany",
                                                   "--format", "json", "--max-results", "5")
parts["step_detect_class_hasmany.txt"] = run_cli("--detect", "class HasMany",
                                                 "--format", "json", "--max-results", "5")
parts["step_detect_add_reflection.txt"] = run_cli("--detect", "add_reflection",
                                                  "--format", "json", "--max-results", "5")
parts["step_detect_def_reader.txt"] = run_cli("--detect", "def reader",
                                              "--format", "json", "--max-results", "5")
parts["step_detect_define_rw.txt"] = run_cli("--detect", "define_readers|define_writers|define_accessors",
                                             "--format", "json", "--max-results", "5")
parts["step_detect_create_build.txt"] = run_cli("--detect", "def create_|def build_|def reload_|def reset_",
                                                "--format", "json", "--max-results", "5")
parts["step_detect_create_build2.txt"] = run_cli("--detect", "def create|def build",
                                                 "--format", "json", "--max-results", "5")
# Shell reads
parts["step_read_assoc_1420_1434.txt"] = read_range(
    "activerecord/lib/active_record/associations.rb", 1420, 1434)
parts["step_read_collection_assoc.txt"] = read_range(
    "activerecord/lib/active_record/associations/collection_association.rb", 1, 528)
parts["step_read_assoc_1180_1259.txt"] = read_range(
    "activerecord/lib/active_record/associations.rb", 1180, 1259)
parts["step_read_builder_hasmany.txt"] = read_range(
    "activerecord/lib/active_record/associations/builder/has_many.rb", 1, 23)
parts["step_read_hm_assoc.txt"] = read_range(
    "activerecord/lib/active_record/associations/has_many_association.rb", 1, 167)
parts["step_read_assoc_1340_1439.txt"] = read_range(
    "activerecord/lib/active_record/associations.rb", 1340, 1439)
parts["step_read_assoc_1100_1179.txt"] = read_range(
    "activerecord/lib/active_record/associations.rb", 1100, 1179)
parts["step_read_builder_coll_assoc.txt"] = read_range(
    "activerecord/lib/active_record/associations/builder/collection_association.rb", 1, 84)
parts["step_read_builder_assoc.txt"] = read_range(
    "activerecord/lib/active_record/associations/builder/association.rb", 1, 181)
parts["step_read_reflection_890_969.txt"] = read_range(
    "activerecord/lib/active_record/reflection.rb", 890, 969)
parts["step_read_builder_singular.txt"] = read_range(
    "activerecord/lib/active_record/associations/builder/singular_association.rb", 1, 76)
parts["step_read_coll_proxy_310_389.txt"] = read_range(
    "activerecord/lib/active_record/associations/collection_proxy.rb", 310, 389)

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