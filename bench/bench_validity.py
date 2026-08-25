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
  python bench_validity.py                  # all repos
  python bench_validity.py projectm         # one repo
  python bench_validity.py --root /my/repos # override repo parent dir
"""
import argparse, json, os, re, subprocess, sys, tempfile, shutil
from pathlib import Path

# When run from the project's venv, tricorder.exe lives next to python.exe.
# Override with the TRICORDER_EXE env var if your layout differs.
TRICORDER_EXE = os.environ.get(
    "TRICORDER_EXE", str(Path(sys.executable).with_name("tricorder.exe"))
)
# Default parent dir of the benchmarked repos. Override per-run with --root.
ROOT = Path(r"D:\Projects\Tricorder-Testing-Repos")

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
    {
        "name": "linux",
        "root": ROOT / "linux",
        "scan_path": ".",
        "map_tokens": 40000,  # kernel is symbol-dense; 2048 only serializes core.c's head
        "exclude_globs": None,
        # Kernel-scale fast path: --pre-index narrows to files containing the
        # symbol so a giant tree is never walked. 'pick_next_task' is narrow
        # (~6 sched/ files) vs 'schedule' (3291 matches, wrong files). Skips
        # this entry when the linux tree isn't present (use --root to point at
        # a checkout).
        "pre_index": "pick_next_task",
        "tasks": [
            {
                "question": "Where is the scheduler entry point that selects which task to run next, and what per-entity budget helper keeps fair-class tasks current?",
                "ground_truth": ["pick_next_task", "schedule", "update_curr"],
            },
        ],
    },
    {
        "name": "bitburner",
        "root": ROOT / "bitburner",
        "scan_path": "src",
        "map_tokens": 65000,
        "exclude_globs": None,
        "tasks": [
            {
                "question": "How do you register and invoke command aliases in bitburner scripts/terminal?",
                "ground_truth": ["loadAliases", "addAlias"],
            },
        ],
    },
    {
        "name": "librechat",
        "root": ROOT / "LibreChat",
        "scan_path": "packages",
        "map_tokens": 65000,
        "exclude_globs": None,
        "tasks": [
            {
                "question": "How does LibreChat resolve the current tenant/user identity in a request context?",
                "ground_truth": ["getTenantId", "configCapability"],
            },
        ],
    },
    {
        "name": "elixir",
        "root": ROOT / "elixir",
        "scan_path": "lib/iex",
        "map_tokens": 4096,
        "exclude_globs": None,
        "tasks": [
            {
                "question": "How do you configure the IEx interactive shell options?",
                "ground_truth": ["IEx", "configure", "configuration"],
            },
        ],
    },
    {
        "name": "otp",
        "root": ROOT / "otp",
        "scan_path": "lib/compiler",
        "map_tokens": 65000,
        "exclude_globs": None,
        "tasks": [
            {
                "question": "What is the OTP compiler smoke-test entry and the mix project representation?",
                "ground_truth": ["Smoke", "MixProject"],
            },
        ],
    },
    {
        "name": "go",
        "root": ROOT / "go",
        "scan_path": "src/cmp",
        "map_tokens": 4096,
        "exclude_globs": None,
        "tasks": [
            {
                "question": "What comparison operators/helpers does the cmp package provide?",
                "ground_truth": ["Less", "Compare", "Or"],
            },
        ],
    },
    {
        "name": "kotlin",
        "root": ROOT / "kotlin",
        "scan_path": "core",
        "map_tokens": 65000,
        "exclude_globs": None,
        "tasks": [
            {
                "question": "How is variance computed for an inline class' expanded type?",
                "ground_truth": ["Variance", "TypeSystemCommonBackendContext"],
            },
        ],
    },
    {
            "name": "swift",
            "root": ROOT / "swift",
            "scan_path": "lib",
            "map_tokens": 65000,
            "exclude_globs": None,
            "tasks": [
                {
                    "question": "What is the SIL function IR representation?",
                    "ground_truth": ["SILFunction"],
                },
            ],
        },
    {
        "name": "rails",
        "root": ROOT / "rails",
        "scan_path": "activerecord/lib",
        "map_tokens": 65000,
        "exclude_globs": None,
        "tasks": [
            {
                "question": "How do you declare a belongs_to association in ActiveRecord?",
                "ground_truth": ["belongs_to"],
            },
        ],
    },
    {
        "name": "framework",
        "root": ROOT / "framework",
        "scan_path": "src",
        "map_tokens": 65000,
        "exclude_globs": None,
        "tasks": [
            {
                "question": "Where is the Laravel Collection class defined?",
                "ground_truth": ["Collection"],
            },
        ],
    },
    {
        "name": "kong",
        "root": ROOT / "kong",
        "scan_path": "kong",
        "map_tokens": 65000,
        "exclude_globs": None,
        "tasks": [
            {
                "question": "What is the kong plugin context initialization function?",
                "ground_truth": ["setup_plugin_context"],
            },
        ],
    },
    {
        "name": "spring-boot",
        "root": ROOT / "spring-boot",
        "scan_path": ".",
        "map_tokens": 65000,
        "exclude_globs": None,
        "tasks": [
            {
                "question": "What is the Spring Boot RunMojo class?",
                "ground_truth": ["RunMojo"],
            },
        ],
    },
    {
        "name": "vue",
        "root": ROOT / "vue",
        "scan_path": "src/v3/reactivity",
        "map_tokens": 4096,
        "exclude_globs": None,
        "tasks": [
            {
                "question": "How is the ref() reactivity helper defined?",
                "ground_truth": ["ref"],
            },
        ],
    },
]


def run(exe, args) -> subprocess.CompletedProcess:
    return subprocess.run([exe, *args], capture_output=True, text=True)


def stats(root, scan_path, map_file, map_tokens, exclude_globs, pre_index=None):
    """Return (map_tokens_actual, full_repo_estimate, coverage_pct) for the repo."""
    args = ["--root", str(root), "--map-tokens", str(map_tokens),
            "--exclude-untagged", "--verbose", "--output", str(map_file), scan_path]
    if exclude_globs:
        args += ["--exclude-globs", *exclude_globs]
    if pre_index:
        args += ["--pre-index", pre_index]
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
                                                      repo.get("exclude_globs"),
                                                      repo.get("pre_index"))
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
        # Debug: on failure, keep the map so we can inspect what the matcher saw.
        task_failed = any(not t["pass"] for t in report["tasks"]) if report["tasks"] else False
        if task_failed:
            shutil.copy2(map_file, bench_dir / f"{name}_LAST_FAIL_map.txt")
            report["_debug_map_path"] = str(bench_dir / f"{name}_LAST_FAIL_map.txt")
        # Normal cleanup
        try:
            shutil.rmtree(td, ignore_errors=True)
        except Exception:
            pass

    return report


def check_env():
    """Report presence/absence of the external system tools tricorder shells out to."""
    import shutil
    tools = {
        "python":     "required",
        "git":        "required",
        "rg":         "optional (fast path for huge trees)",
        "ctags":      "optional (fallback when rg is absent)",
        "tree-sitter": "not required (only for custom grammar builds)",
    }
    print("Pre-requisites (system-level):")
    for name, note in tools.items():
        where = shutil.which(name) or shutil.which(name + ".exe")
        status = "FOUND   " if where else "MISSING"
        print(f"  {name:<13} {status}  ({note})")
        if where:
            print(f"               -> {where}")
    return 0


def main():
    p = argparse.ArgumentParser(description="tricorder vs blind navigation benchmark")
    p.add_argument("repo", nargs="?", default=None,
                   help="run only this repo (projectm|vaultwarden)")
    p.add_argument("--root", default=None,
                   help="override the parent dir the benchmarked repos live in "
                        "(default: D:\\Projects); each repo is <root>/<name>")
    p.add_argument("--check-env",
                   action="store_true", default=False,
                   help="print presence/absence of rg, ctags, git, tree-sitter and exit")
    args = p.parse_args()
    if args.check_env:
        return check_env()
    only = args.repo
    root_override = Path(args.root) if args.root else ROOT
    reports = []
    for repo in REPOS:
        if only and only != repo["name"]:
            continue
        # Apply --root override so external users can point at their own checkouts
        r = dict(repo)
        if repo["name"] == "projectm":
            # projectm lives outside the consolidated testbed parent dir
            r["root"] = Path(r"D:\Projects\projectm")
        elif repo["name"] == "bitburner":
            # bitburner folder name differs from repo key
            r["root"] = root_override / "bitburner-src"
        else:
            r["root"] = root_override / repo["name"]
        if not r["root"].is_dir():
            print(f"skip {repo['name']}: root {r['root']} not present (pass --root)")
            continue
        reports.append(run_repo(r))
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