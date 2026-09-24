#!/usr/bin/env python3
"""Meter B-Rails-Q1 attempt 1 from the recalled command list."""
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))
from utils import count_tokens

RAILS = Path(r"D:\Projects\Tricorder-Testing-Repos\rails")
OUT = Path(__file__).resolve().parent
AR = "activerecord/lib/active_record"


def read_range(rel, offset, limit):
    lines = (RAILS / rel).read_text(encoding="utf-8").splitlines()
    return "\n".join(lines[offset - 1:offset - 1 + limit])


def grep_rb(subdir, pattern):
    out = []
    for p in sorted((RAILS / subdir).rglob("*.rb")):
        try:
            lines = p.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        for i, ln in enumerate(lines, 1):
            if re.search(pattern, ln):
                out.append(f"{p.relative_to(RAILS).as_posix()}:{i}:{ln}")
    return "\n".join(out)


def assoc_names():
    return "\n".join(sorted(
        str(p.relative_to(RAILS / AR))
        for p in (RAILS / AR).rglob("*association*")))


def builder_names():
    return "\n".join(sorted(
        p.name for p in (RAILS / AR / "associations/builder").iterdir()))


parts = {}
parts["step01_assoc_tree.txt"] = assoc_names()
parts["step02_builder_ls.txt"] = builder_names()
parts["step03_read_coll_builder.txt"] = read_range(
    f"{AR}/associations/builder/collection_association.rb", 1, 84)
parts["step04_read_assoc_builder.txt"] = read_range(
    f"{AR}/associations/builder/association.rb", 1, 181)
parts["step05_read_hm_builder.txt"] = read_range(
    f"{AR}/associations/builder/has_many.rb", 1, 23)
parts["step06_read_hma.txt"] = read_range(
    f"{AR}/associations/has_many_association.rb", 1, 167)
parts["step07_read_coll_assoc.txt"] = read_range(
    f"{AR}/associations/collection_association.rb", 1, 528)
parts["step08_read_assoc.txt"] = read_range(
    f"{AR}/associations/association.rb", 1, 438)
parts["step09_grep_def_hm.txt"] = grep_rb(
    "activerecord/lib/active_record", r"def has_many\b")
parts["step10_read_entry.txt"] = read_range(
    f"{AR}/associations.rb", 1420, 50)
parts["step11_grep_refl.txt"] = grep_rb(
    "activerecord/lib/active_record", r"class.*Reflection")
parts["step12_read_assoc_refl.txt"] = read_range(
    f"{AR}/reflection.rb", 496, 150)
parts["step13_read_hm_refl.txt"] = read_range(
    f"{AR}/reflection.rb", 890, 100)
parts["step14_grep_collproxy.txt"] = grep_rb(
    "activerecord/lib", r"class CollectionProxy")
parts["step15_grep_assocproxy_lib.txt"] = grep_rb(
    "activerecord/lib", r"class AssociationProxy")
parts["step16_read_collproxy.txt"] = read_range(
    f"{AR}/associations/collection_proxy.rb", 1, 120)
parts["step17_read_singular.txt"] = read_range(
    f"{AR}/associations/singular_association.rb", 1, 75)
parts["step18_grep_reader.txt"] = grep_rb(
    "activerecord/lib/active_record/associations", r"def reader")
parts["step19_read_hasone.txt"] = read_range(
    f"{AR}/associations/has_one_association.rb", 1, 151)
parts["step20_read_foreign.txt"] = read_range(
    f"{AR}/associations/foreign_association.rb", 1, 42)
parts["step21_read_sing_builder.txt"] = read_range(
    f"{AR}/associations/builder/singular_association.rb", 1, 76)
parts["step22_grep_assocproxy_all.txt"] = grep_rb(".", r"AssociationProxy")
parts["step23_read_assoc_rel.txt"] = read_range(
    f"{AR}/association_relation.rb", 1, 51)
parts["step24_read_refl_head.txt"] = read_range(
    f"{AR}/reflection.rb", 1, 55)
parts["step25_read_scope.txt"] = read_range(
    f"{AR}/associations/association_scope.rb", 1, 185)

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