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

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

TESTBED = Path(r"D:\Projects\Tricorder-Testing-Repos")
DBDIR = Path(r"D:\Projects\tricorder\.tricorder\db")
MAP = {
    "projectm": Path(r"D:\Projects\projectm"),
    "vaultwarden": TESTBED / "vaultwarden",
    "go": TESTBED / "go",
    "kotlin": TESTBED / "kotlin",
    "linux": TESTBED / "linux",
    "rails": TESTBED / "rails",
    "swift": TESTBED / "swift",
    "spring-boot": TESTBED / "spring-boot",
    "repo-map": TESTBED / "repo-map",
    "vue": TESTBED / "vue",
    "SwiftTest": TESTBED / "SwiftTest",
    "SwiftTest2": TESTBED / "SwiftTest2",
    "uplink": TESTBED / "uplink",
    "zombie_survival": TESTBED / "zombie_survival",
}


def disk_files(root):
    # Single source of truth: the scanner's own discovery (utils.
    # discover_src_files) — its docstring says "one implementation, two
    # callers — no drift", and this is caller #2. The old private os.walk
    # with an EXTS allowlist disagreed with the scanner everywhere (it
    # missed .gradle/.cjs/dotfiles the scanner reads) and printed scan%
    # >100%. ponytail: reuse, don't re-walk.
    from utils import discover_src_files
    report = {}
    files = discover_src_files(str(root), use_gitignore=True, report=report)
    out = {os.path.relpath(f, str(root)) for f in files}
    # Only a "warning" key means the walk actually truncated; the stats
    # keys (files_considered, ...) are always present.
    return out, "warning" in report


def serving_db(repo, root):
    # Same precedence as the server (_canonical_db_for): testbed-local
    # <root>/.tricorder/db/<name>.db first, central cache fallback.
    # The audit must check the DB that actually serves queries.
    local = Path(root) / ".tricorder" / "db" / f"{repo}.db"
    if local.exists():
        return local, "local"
    return DBDIR / f"{repo}.db", "central"


def audit(repo, root):
    db, which = serving_db(repo, root)
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
        try:
            scanned = {r[0] for r in con.execute(
                "SELECT DISTINCT rel_file FROM file_state")}
            no_fstate = False
        except sqlite3.OperationalError:
            scanned = set()  # pre-file_state DB: scan coverage unverifiable
            no_fstate = True
        try:
            xrow = con.execute(
                "SELECT extractor_version FROM meta ORDER BY rowid DESC LIMIT 1"
            ).fetchone()
            xver = xrow[0] if xrow else 0
        except sqlite3.OperationalError:
            xver = 0  # pre-feature DB: staleness unknown, human decides
    finally:
        con.close()
    disk, capped = disk_files(root) if root.exists() else (set(), False)
    norm = {p.replace("\\", "/") for p in disk}
    scanned_norm = {t.replace("\\", "/") for t in scanned}
    tagged_norm = {t.replace("\\", "/") for t in tagged}
    # Two honest numbers: unscanned = cap never reached the file;
    # tagless = scanned but tree-sitter yielded no symbols (.sh, .pl...).
    # The old disk-vs-tags MISSING conflated the two and indicted the cap
    # for files like compile.sh that were scanned and simply tagless.
    unscanned = sorted(norm - scanned_norm) if norm else []
    tagless = len(scanned_norm - tagged_norm)
    return {"repo": repo, "meta_rows": meta, "tags": tags, "refs": refs,
            "scanned_files": len(scanned_norm),
            "tagged_files": len(tagged_norm), "disk_files": len(norm),
            "walk_capped": capped, "no_fstate": no_fstate, "which": which,
            "tagless": tagless, "xver": xver,
            "unscanned_sample": unscanned[:10], "unscanned_total": len(unscanned),
            "secs": round(time.time() - t0, 1)}


def main():
    args = sys.argv[1:]
    # --stamp is a HUMAN assertion ("I verified these tags are current"),
    # used once to baseline DBs the archaeology already cleared. It never
    # runs automatically: nothing may certify tags except a full reparse.
    if args and args[0] == "--stamp":
        from database import EXTRACTOR_VERSION
        if len(args) < 2:
            print("usage: coverage_audit.py --stamp <repo> [<repo>...]")
            sys.exit(2)
        for repo in args[1:]:
            if repo not in MAP:
                print(f"{repo:12} unknown repo (not in MAP)")
                continue
            db = DBDIR / f"{repo}.db"
            if not db.exists():
                print(f"{repo:12} no DB")
                continue
            con = sqlite3.connect(str(db))
            try:
                cols = {r[1] for r in con.execute("PRAGMA table_info(meta)")}
                if "extractor_version" not in cols:
                    con.execute("ALTER TABLE meta ADD COLUMN extractor_version"
                                " INTEGER NOT NULL DEFAULT 0")
                con.execute("UPDATE meta SET extractor_version=?",
                            (EXTRACTOR_VERSION,))
                con.commit()
                print(f"{repo:12} stamped v{EXTRACTOR_VERSION} (human-verified)")
            finally:
                con.close()
        return
    only = args[0] if args else None
    from database import EXTRACTOR_VERSION
    print(f"{'repo':12} {'meta':>4} {'tags':>9} {'refs':>10} "
          f"{'scanned':>7} {'disk':>7} {'scan%':>6} {'tagless':>7}  flags")
    for repo, root in MAP.items():
        if only and repo != only:
            continue
        r = audit(repo, root)
        if "error" in r:
            print(f"{repo:12} {r['error']}")
            continue
        cov = (100.0 * r["scanned_files"] / r["disk_files"]
               if r["disk_files"] and not r["walk_capped"] else None)
        flags = []
        if r["meta_rows"] > 1:
            flags.append(f"STACKEDx{r['meta_rows']}")
        if r["walk_capped"]:
            flags.append("WALK-CAPPED")
        if r["no_fstate"]:
            flags.append("NO-FSTATE")
        if r["xver"] == 0:
            flags.append("UNSTAMPED")
        elif r["xver"] != EXTRACTOR_VERSION:
            flags.append(f"STALE-v{r['xver']}")
        if r["unscanned_total"]:
            flags.append(f"UNSCANNED{r['unscanned_total']}")
        if r["refs"] == 0:
            flags.append("NO-REFS")
        if r["which"] == "local":
            flags.append("LOCAL")
        cov_s = f"{cov:>5.1f}%" if cov is not None else "   n/a"
        print(f"{repo:12} {r['meta_rows']:>4} {r['tags']:>9,} "
              f"{r['refs']:>10,} {r['scanned_files']:>7,} "
              f"{r['disk_files']:>7,} {cov_s} {r['tagless']:>7,}  "
              f"{' '.join(flags)} ({r['secs']}s)")
        if r["unscanned_sample"]:
            for m in r["unscanned_sample"][:5]:
                print(f"               e.g. unscanned: {m}")
    print("\nDone. STACKED = meta rows >1 (appended scans). "
          "UNSCANNED = on disk, never reached file_state (cap/regression). "
          "tagless = scanned but zero symbols (scripts, data — normal). "
          "UNSTAMPED = pre-feature DB (human decides); STALE-vN = extractor "
          "moved on, rescan via chunk protocol.")


if __name__ == "__main__":
    main()
