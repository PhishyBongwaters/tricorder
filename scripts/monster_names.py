#!/usr/bin/env python3
"""Quantify monster-name tags in a tricorder DB."""
import sqlite3
import sys

db = sys.argv[1] if len(sys.argv) > 1 else ".tricorder/db/rails.db"
c = sqlite3.connect(db)
print("max name len =", c.execute("SELECT MAX(LENGTH(name)) FROM tags").fetchone()[0])
for thresh in (200, 500, 2000):
    n = c.execute("SELECT COUNT(*) FROM tags WHERE LENGTH(name)>?", (thresh,)).fetchone()[0]
    print(f"names>{thresh} chars =", n)
rows = c.execute(
    "SELECT rel_file, line, LENGTH(name), SUBSTR(name,1,80) FROM tags "
    "WHERE LENGTH(name)>500 LIMIT 5").fetchall()
for r in rows:
    print(r)
