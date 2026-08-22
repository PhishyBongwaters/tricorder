#!/usr/bin/env python3
"""
bench_validity.py — tricorder vs blind navigation test.

Proves, across multiple real repos, that a tricorder T0 map steers an agent
to the correct code without reading the full repo.

For each repo + task:
  - RUN  tricorder generates a T0 map (definitions + signatures only)
  - CHECK  the map contains the ground-truth identifiers/symbols that answer
           the task -> if present, grading is "valid steering"
  - COST  full-repo token estimate (what a blind agent must read) vs map tokens

Exit 0 if all tasks PASS (map contains every required identifier).
Exit 1 otherwise. Prints a table.

Usage:
  python bench_validity.py            # all repos
  python bench_validity.py projectm   # one repo
"""
import json, os, re, subprocess, sys, tempfile, shutil
from pathlib import Path

TRICORDER_EXE = r"D:\Projects\tricorder\.venv\Scripts\tricorder.exe"
ROOT = Path(r"D:\Projects")

# Each task: a realistic question an agent would answer while "working" on the
# repo. ground_truth = identifiers/symbols/icons that MUST appear in the map
# for the task to be answerable from the map (i.e. not blind guesswork).
REPOS = [
    {
        "name": "projectm",
        "root": ROOT / "projectm",
        "scan_path": "src/libprojectM",
        "map_tokens": 2048,
        "exclude_globs": None,
        "tasks": [
            {
                "question": "Where is the audio-injection entry point, and what overloads does an app call to feed PCM samples?",
                "ground_truth": ["PCM::AddToBuffer", "AddToBuffer"],
            },
            {
                "question": "What class computes loudness bands from the spectrum?",
                "ground_truth": ["Loudness", "CurrentRelative", "AverageRelative"],
            },
        ],
    },
    {
        "name": "vaultwarden",
        "root": ROOT / "vaultwarden",
        "scan_path": "src",
        "map_tokens": 32768,
        "exclude_globs": None,
        "tasks": [
            {
                "question": "What is the admin invite/user-management handler, and where do password hashing primitives live?",
                "ground_truth": ["generate_invite", "delete_user", "admin_page", "hash_password", "verify_password_hash"],
            },
            {
                "question": "What route handler registers the /api token endpoints?",
                "ground_truth": ["routes", "catchers"],
            },
        ],
    },
]


def run(exe, args) -> subprocess.CompletedProcess:
    return subprocess.run([exe, *args], capture_output=True, text=True)


def stats(root, scan_path, map_file, map_tokens, exclude_globs):
    """Return (map_tokens_actual, full_repo_estimate, coverage_pct) for the repo."""
    args = ["--root", str(root), "--map-tokens", str(map_tokens),
            "--exclude-untagged", "--verbose", "--output", str(map_file), scan_path]
    if exclude_globs:
        args += ["--exclude-globs", *exclude_globs]
    r = run(TRICORDER_EXE, args)
    map_tokens_actual = 0
    coverage_pct = 0.0
    # Parse the CLI output for actual map tokens and coverage
    if r.returncode == 0:
        # Parse output like "Repo-map: 2.1 k-tokens" and "Warning: Low map coverage: ..."
        # Check both stdout and stderr for the Repo-map line
        output = r.stdout + "\n" + r.stderr
        for line in output.split('\n'):
            if "Repo-map:" in line and "k-tokens" in line:
                # Parse "Repo-map: 2.1 k-tokens"
                match = re.search(r'Repo-map:\s*([\d.]+)\s*k-tokens', line)
                if match:
                    map_tokens_actual = int(float(match.group(1)) * 1024)
            elif "Repo-map:" in line and "tokens" in line:
                # Parse "Repo-map: X tokens"
                match = re.search(r'Repo-map:\s*(\d+)\s*tokens', line)
                if match:
                    map_tokens_actual = int(match.group(1))
            elif "Low map coverage:" in line:
                # Parse "Low map coverage: X/Y source files (Z%)"
                match = re.search(r'Low map coverage: (\d+)/(\d+) source files \(([\d.]+)%\)', line)
                if match:
                    coverage_pct = float(match.group(3))
    full_repo = repo_budget(root, exclude_globs)
    return map_tokens_actual, full_repo, coverage_pct


def repo_budget(root, exclude_globs):
    args = ["--root", str(root), "--stats-only"]
    if exclude_globs:
        args += ["--exclude-globs", *exclude_globs]
    r = run(TRICORDER_EXE, args)
    try:
        return json.loads(r.stdout)["full_repo_estimate"]
    except Exception:
        return 0


def norm(s: str) -> str:
    # identifier searching: strip whitespace/case, keep alnum + ::_/.\-+
    return "".join(c.lower().replace(" ", "")
                   for c in s if c.isalnum() or c in "::_./-+")


def identifier_present(maptext, ident) -> bool:
    n = norm(ident)
    # map lines are "  NNN: <signature>" — the identifier usually leads the sig.
    # be lenient: check the identifier token appears as a std::free-standing form.
    mt = norm(maptext)
    return n in mt


def run_repo(repo) -> dict:
    name = repo["name"]
    root = repo["root"]
    scan = repo["scan_path"]
    mt = repo["map_tokens"]
    report = {"name": name, "tasks": []}

    # Use project directory for temp to avoid Windows permission issues
    bench_dir = Path.cwd() / "bench_temp"
    bench_dir.mkdir(exist_ok=True)
    td = tempfile.mkdtemp(prefix=f"bench_{name}_", dir=bench_dir)
    try:
        map_file = Path(td) / "map.txt"
        map_tokens_actual, full_repo, coverage_pct = stats(root, scan, map_file, mt,
                                              repo.get("exclude_globs"))
        map_text = map_file.read_text(encoding="utf-8", errors="replace") if map_file.exists() else ""

        for t in repo["tasks"]:
            missing = []
            for ident in t["ground_truth"]:
                if not norm(ident) in norm(map_text):
                    missing.append(ident)
            passes = not missing
            report["tasks"].append({
                "question": t["question"],
                "pass": passes,
                "missing": missing,
            })

        report["map_tokens"] = map_tokens_actual
        report["full_repo_tokens"] = full_repo
        report["savings_pct"] = round(
            max(0.0, 1 - map_tokens_actual / full_repo) * 100, 1
        ) if full_repo else 0.0
        report["coverage_pct"] = coverage_pct

    finally:
        # Clean up temp directory
        try:
            shutil.rmtree(td, ignore_errors=True)
        except Exception:
            pass

    return report


def main():
    only = sys.argv[1] if len(sys.argv) > 1 else None
    reports = []
    for repo in REPOS:
        if only and only != repo["name"]:
            continue
        reports.append(run_repo(repo))
        print(f"ran {repo['name']}")

    print()
    print(f"{'repo':<14}{'task#':<6}{'PASS?':<6}{'map_tok':<10}{'full_tok':<12}{'savings':<9}")
    print("-" * 60)
    all_pass = True
    for r in reports:
        for i, t in enumerate(r["tasks"], 1):
            all_pass = all_pass and t["pass"]
            print(f"{r['name']:<14}{i:<6}{'PASS' if t['pass'] else 'FAIL':<6}"
                  f"{r['map_tokens']:<10}{r['full_repo_tokens']:<12}{r['savings_pct']:<9}")
        if not r["tasks"]:
            print(f"{r['name']:<14}{'-':<6}{'-':<6}{r['map_tokens']:<10}{r['full_repo_tokens']:<12}{r['savings_pct']:<9}")
    print("-" * 60)
    cred = "ALL TASKS PASS" if all_pass else "SOME TASKS FAIL"
    print(f"RESULT: {cred}")
    for r in reports:
        for t in r["tasks"]:
            if not t["pass"]:
                print(f"  [{r['name']}] MISSING in map: {t['missing']}")
                print(f"      Q: {t['question']}")
    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())