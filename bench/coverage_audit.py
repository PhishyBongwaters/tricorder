#!/usr/bin/env python3
"""coverage_audit.py — read-only DB-vs-disk coverage audit (no quota, no writes).

For each tricorder sqlite DB: distinct tagged files vs actual source files
on disk, meta-row stacking check, ref-edge totals. Quantifies "full map
isn't everything" before any rescan.

Usage:
  python bench/coverage_audit.py            # all known DBs
  python bench/coverage_audit.py projectm   # one repo
"""
import os
import sqlite3
import sys
import time
from pathlib import Path

TESTBED = Path(r"D:\Projects\Tricorder-Testing-Repos")
DBDIR = Path(r"D:\Projects\tricorder\.tricorder\db")
MAP = {
    "projectm": Path(r"D:\Projects\projectm"),
    "go": TESTBED / "go",
    "kotlin": TESTBED / "kotlin",
    "linux": TESTBED / "linux",
    "rails": TESTBED / "rails",
    "swift": TESTBED / "swift",
    "vaultwarden": TESTBED / "vaultwarden",
}
EXTS = {".cpp", ".hpp", ".h", ".c", ".cc", ".cxx", ".hxx", ".rs", ".py",
        ".go", ".kt", ".kts", ".java", ".js", ".ts", ".tsx", ".rb", ".swift",
        ".m", ".mm", ".cs", ".php", ".ex", ".exs", ".erl", ".hrl", ".vue",
        ".scala", ".pl", ".pm", ".sh", ".lua", ".r", ".jl", ".dart"}
MAX_WALK = 20000  # same early-stop as tricorder's TRICORDER_MAX_SCAN_FILES


def disk_files(root):
    out, stopped = set(), False
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames
                       if d not in (".git", ".tricorder", "node_modules",
                                    "target", ".hg", ".svn", "out", "dist")
                       and not d.startswith("build")]
        for fn in filenames:
            if Path(fn).suffix.lower() in EXTS:
                out.add(os.path.relpath(os.path.join(dirpath, fn), root))
                if len(out) >= MAX_WALK:
                    stopped = True
                    break
        if stopped:
            break
    return out, stopped


def audit(repo, root):
    db = DBDIR / f"{repo}.db"
    if not db.exists():
        return {"repo": repo, "error": "no DB (never scanned?)"}
    t0 = time.time()
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        meta = con.execute("SELECT COUNT(*) FROM meta").fetchone()[0]
        tags = con.execute("SELECT COUNT(*) FROM tags").fetchone()[0]
        refs = con.execute("SELECT COUNT(*) FROM refs").fetchone()[0]
        tagged = {r[0] for r in
                  con.execute("SELECT DISTINCT rel_file FROM tags")}
    finally:
        con.close()
    disk, capped = disk_files(root) if root.exists() else (set(), False)
    norm = {p.replace("\\", "/") for p in disk}
    tagged_norm = {t.replace("\\", "/") for t in tagged}
    missing = sorted(norm - tagged_norm) if norm else []
    return {"repo": repo, "meta_rows": meta, "tags": tags, "refs": refs,
            "tagged_files": len(tagged_norm), "disk_files": len(norm),
            "walk_capped": capped,
            "missing_sample": missing[:10], "missing_total": len(missing),
            "secs": round(time.time() - t0, 1)}


def main():
    only = sys.argv[1] if len(sys.argv) > 1 else None
    print(f"{'repo':12} {'meta':>4} {'tags':>9} {'refs':>10} "
          f"{'tagged':>7} {'disk':>7} {'cov%':>6}  flags")
    for repo, root in MAP.items():
        if only and repo != only:
            continue
        r = audit(repo, root)
        if "error" in r:
            print(f"{repo:12} {r['error']}")
            continue
        cov = (100.0 * r["tagged_files"] / r["disk_files"]
               if r["disk_files"] else 0)
        flags = []
        if r["meta_rows"] > 1:
            flags.append(f"STACKEDx{r['meta_rows']}")
        if r["walk_capped"]:
            flags.append("WALK-CAPPED")
        if r["missing_total"]:
            flags.append(f"MISSING{r['missing_total']}")
        if r["refs"] == 0:
            flags.append("NO-REFS")
        print(f"{repo:12} {r['meta_rows']:>4} {r['tags']:>9,} "
              f"{r['refs']:>10,} {r['tagged_files']:>7,} "
              f"{r['disk_files']:>7,} {cov:>5.1f}%  {' '.join(flags)} "
              f"({r['secs']}s)")
        if r["missing_sample"]:
            for m in r["missing_sample"][:5]:
                print(f"               e.g. missing: {m}")
    print("\nDone. STACKED = meta rows >1 (appended scans). "
          "MISSING = on disk, not in tags.")


if __name__ == "__main__":
    main()
