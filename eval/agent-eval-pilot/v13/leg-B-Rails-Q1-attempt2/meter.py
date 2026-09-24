#!/usr/bin/env python3
"""Meter B-Rails-Q1 attempt 2 from the returned command list (16 steps)."""
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))
from utils import count_tokens

REPO = Path(r"D:\Projects\Tricorder-Testing-Repos\rails")
AR = "activerecord/lib/active_record"
OUT = Path(__file__).resolve().parent


def listing(rel):
    return "\n".join(sorted(p.name for p in (REPO / rel).iterdir()))


def grep(pattern):
    out = []
    for p in sorted((REPO / "activerecord").rglob("*.rb")):
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
parts["step01_ls_rails.txt"] = listing(".")
parts["step02_ls_activerecord.txt"] = listing("activerecord")
parts["step03_grep_hasmany.txt"] = grep(r"def has_many")
parts["step04_read_assoc_1400_1549.txt"] = read_range(
    AR + "/associations.rb", 1400, 1549)
parts["step05_grep_class_hasmany.txt"] = grep(r"class HasMany")
parts["step06_grep_module_builder.txt"] = grep(r"module Builder")
parts["step07_read_assoc_18_117.txt"] = read_range(AR + "/associations.rb", 18, 117)
parts["step08_read_builder_hasmany.txt"] = read_all(
    AR + "/associations/builder/has_many.rb")
parts["step09_read_builder_coll_assoc.txt"] = read_all(
    AR + "/associations/builder/collection_association.rb")
parts["step10_read_builder_assoc.txt"] = read_all(
    AR + "/associations/builder/association.rb")
parts["step11_grep_hm_assoc.txt"] = grep(r"class HasManyAssociation")
parts["step12_read_hm_assoc.txt"] = read_all(
    AR + "/associations/has_many_association.rb")
parts["step13_grep_coll_assoc.txt"] = grep(r"class CollectionAssociation")
parts["step14_read_coll_assoc.txt"] = read_all(
    AR + "/associations/collection_association.rb")
parts["step15_grep_gen_assoc.txt"] = grep(r"def generated_association_methods")
parts["step16_read_assoc_runtime.txt"] = read_all(
    AR + "/associations/association.rb")

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