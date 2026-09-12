#!/usr/bin/env python3
"""Serial rising-cap chunk loop: one command to full coverage.

Usage: chunk_resume.py <repo-path> [--start-cap N] [--step N] [--timeout S]

Loops `tricorder.py --db-path <canonical> --max-files <cap>` with a rising
cap (fixed-cap reruns add zero rows — coverage grows only when the cap
exceeds the mapped count). After each chunk, reads DISTINCT file/tag/ref
counts from the DB; stops when mapped == discovered total (DONE) or when
two consecutive chunks add zero files (STALL, exit 1). Serial, one run at
a time — no worker pool, no DB merge.

DB path comes from `tricorder.py --init --root` (item 2); never hardcoded.
"""
import argparse
import sqlite3
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from utils import discover_src_files

TRICORDER = Path(__file__).resolve().parent / "tricorder.py"


def db_counts(db: Path):
    """(scanned_files, tag_files, tags, refs). scanned = file_state rows (every
    parsed file, even tagless ones like `x = 1`); tag coverage alone stalls on
    tagless files. Missing DB = zeros; never connect blind (sqlite creates a
    0-byte file on connect, masking real absence)."""
    if not db.exists():
        return (0, 0, 0, 0)
    conn = sqlite3.connect(str(db))
    try:
        scanned = conn.execute("SELECT COUNT(*) FROM file_state").fetchone()[0]
        tag_files = conn.execute("SELECT COUNT(DISTINCT rel_file) FROM tags").fetchone()[0]
        tags = conn.execute("SELECT COUNT(*) FROM tags").fetchone()[0]
        refs = conn.execute("SELECT COUNT(*) FROM refs").fetchone()[0]
        return (scanned, tag_files, tags, refs)
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(description="Serial rising-cap scan to full coverage")
    parser.add_argument("repo", help="Repo path to scan")
    parser.add_argument("--start-cap", type=int, default=5000)
    parser.add_argument("--step", type=int, default=5000)
    parser.add_argument("--timeout", type=int, default=3600)
    parser.add_argument("--db-path", default=None,
        help="Resume a custom DB instead of the --init canonical path")
    args = parser.parse_args()

    repo = Path(args.repo).resolve()
    total = len(discover_src_files(str(repo)))

    if args.db_path:
        db = Path(args.db_path)
        db.parent.mkdir(parents=True, exist_ok=True)
    else:
        init = subprocess.run(
            [sys.executable, str(TRICORDER), "--init", "--root", str(repo)],
            capture_output=True, text=True,
        )
        if init.returncode != 0:
            print(f"INIT FAIL: {init.stderr.strip()[-200:]}")
            raise SystemExit(1)
        db = Path(init.stdout.strip())
    out_map = db.with_suffix(".map")

    cap, stall, prev = args.start_cap, 0, -1
    # ponytail: fixed 50-iteration ceiling; bump if a repo ever legitimately
    # needs more than 50 cap steps (50 x 5000 = 250k files).
    for i in range(1, 51):
        proc = subprocess.run(
            [sys.executable, str(TRICORDER), str(repo),
             "--db-path", str(db), "--full", "--output", str(out_map),
             "--max-files", str(cap), "--quiet"],
            capture_output=True, text=True, timeout=args.timeout,
        )
        files, tag_files, tags, refs = db_counts(db)
        print(f"[chunk {i}] cap={cap} scanned={files}/{total} tag_files={tag_files} tags={tags} refs={refs} exit={proc.returncode}", flush=True)
        if files >= total:
            print(f"DONE: {files}/{total} files mapped -> {db}")
            return
        if files <= prev:
            stall += 1
            if stall >= 2:
                print(f"STALL: no growth for 2 chunks at cap={cap} ({files}/{total}). Last stderr: {proc.stderr.strip()[-200:]}")
                raise SystemExit(1)
        else:
            stall = 0
        prev = files
        cap += args.step
    print(f"CEILING: 50 chunks exhausted ({prev}/{total}). Re-run with bigger --step.")
    raise SystemExit(1)


if __name__ == "__main__":
    main()
