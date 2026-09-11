import subprocess, sys, time
repos = sys.argv[1:]
if not repos:
    raise SystemExit("usage: chunk_resume.py <repo> [repo ...]")
for repo in repos:
    print(f"=== {repo} chunked resume ===")
    for attempt in range(1, 7):
        print(f"[{repo}] attempt {attempt}/6 ...")
        cmd = [sys.executable, "pre_scan.py", "--repos", repo]
        try:
            proc = subprocess.run(cmd, timeout=4000)  # let pre_scan handle its own 3600
            print(f"[{repo}] attempt {attempt} exit={proc.returncode} in {time.time():.0f}")
            # Check DB size
            import pathlib
            db = pathlib.Path(f".tricorder/db/{repo}.db")
            if db.exists():
                print(f"[{repo}] db size {db.stat().st_size/1024/1024:.1f} MB")
            # pre_scan returns 0 even on TIMEOUT, so check output: need to parse last run
            # If OK, break. For now break if attempt succeeded with less than 3600 (no timeout)
            # We detect timeout by checking if process timed out -> but we already handle
            # So just check if proc timed out via exception; else assume we need to check logs
            # Simple: if elapsed < 3600, likely OK
        except subprocess.TimeoutExpired:
            print(f"[{repo}] attempt {attempt} TIMEOUT (wrapper) — will resume")
        time.sleep(2)
        # Check if DB now stable - peek at DB file count via sqlite?
        # Just continue loop; next attempt will resume missing files
    print(f"[{repo}] finished loop")
print("ALL DONE")
