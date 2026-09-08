#!/usr/bin/env python3
"""Pre-scan repos: build DB index + full map for each repo in Tricorder-Testing-Repos."""

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

REPOS_DIR = Path(r"D:\Projects\Tricorder-Testing-Repos")
# DBs belong in tricorder's canonical cache root (get_cache_root()), NOT a
# throwaway dir under the testing-repos folder.
from utils import get_cache_root
DB_DIR = get_cache_root() / "db"
TRICORDER = Path(r"D:\Projects\tricorder\tricorder.py")

# projectM is at a different path
PROJECTM = Path(r"D:\Projects\projectm")


def scan_repo(repo_path: Path, db_path: Path) -> dict:
    """Run tricorder --db-path + --full --output on a single repo."""
    out_map = db_path.with_suffix(".map")
    cmd = [
        sys.executable, str(TRICORDER),
        str(repo_path),
        "--db-path", str(db_path),
        "--full",
        "--output", str(out_map),
        "--max-files", "0",
    ]
    t0 = time.time()
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
    elapsed = time.time() - t0
    db_size = db_path.stat().st_size if db_path.exists() else 0
    map_size = out_map.stat().st_size if out_map.exists() else 0
    return {
        "repo": repo_path.name,
        "elapsed_s": round(elapsed, 1),
        "db_bytes": db_size,
        "map_bytes": map_size,
        "ok": result.returncode == 0,
        "stderr": result.stderr.strip() if result.stderr else "",
    }


def main():
    parser = argparse.ArgumentParser(description="Pre-scan repos for tricorder DB index")
    parser.add_argument("--repos", nargs="*", help="Specific repos to scan (default: all)")
    parser.add_argument("--dry-run", action="store_true", help="List repos without scanning")
    args = parser.parse_args()

    DB_DIR.mkdir(exist_ok=True)

    if args.repos:
        repos = [REPOS_DIR / r for r in args.repos]
    else:
        repos = sorted([d for d in REPOS_DIR.iterdir() if d.is_dir() and d.name != "bench_temp"])

    # Add projectM separately
    if PROJECTM.exists():
        repos.append(PROJECTM)

    if args.dry_run:
        for r in repos:
            print(r.name)
        return

    results = []
    for repo in repos:
        db_path = DB_DIR / f"{repo.name}.db"
        print(f"[{repo.name}] scanning...", end=" ", flush=True)
        try:
            res = scan_repo(repo, db_path)
            results.append(res)
            status = "OK" if res["ok"] else f"FAIL ({res['stderr'][:80]})"
            print(f"{res['elapsed_s']}s db={res['db_bytes']/1024:.0f}KB map={res['map_bytes']/1024:.0f}KB {status}")
        except subprocess.TimeoutExpired:
            print("TIMEOUT")
            results.append({"repo": repo.name, "elapsed_s": 600, "db_bytes": 0, "map_bytes": 0, "ok": False, "stderr": "timeout"})
        except Exception as e:
            print(f"ERROR: {e}")
            results.append({"repo": repo.name, "elapsed_s": 0, "db_bytes": 0, "map_bytes": 0, "ok": False, "stderr": str(e)})

    # Summary
    ok = [r for r in results if r["ok"]]
    fail = [r for r in results if not r["ok"]]
    total_time = sum(r["elapsed_s"] for r in ok)
    print(f"\n{'='*60}")
    print(f"Done: {len(ok)}/{len(results)} OK, {len(fail)} failed, {total_time:.0f}s total")
    if fail:
        print("Failures:")
        for r in fail:
            print(f"  {r['repo']}: {r['stderr'][:100]}")


if __name__ == "__main__":
    main()
