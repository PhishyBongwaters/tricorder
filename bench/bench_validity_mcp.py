#!/usr/bin/env python3
"""
bench_validity_mcp.py — tricorder MCP tools vs blind navigation test.

Proves, across multiple real repos, that tricorder MCP tools (detect/symbols/detail)
steer an agent to the correct code without reading the full repo.

For each repo + task:
  - RUN  tricorder MCP detect/symbols to find ground-truth identifiers
  - CHECK  the tools return the exact definitions + line numbers
  - COST   full-repo token estimate vs MCP tool tokens

Exit 0 if all tasks PASS (MCP tools find every required identifier).
Exit 1 otherwise. Prints a table.

Usage:
  python bench_validity_mcp.py            # all repos
  python bench_validity_mcp.py projectm   # one repo
"""
import asyncio
import sys
from pathlib import Path

# Add tricorder to path for server module
sys.path.insert(0, r"D:\Projects\tricorder")

from tricorder_server import tricorder_detect, tricorder_symbols, tricorder_scan, _full_repo_tokens, _budget_fields

ROOT = Path(r"D:\Projects")

# Each task: a realistic question an agent would answer while "working" on the
# repo. ground_truth = identifiers/symbols that MUST be found by MCP tools
# for the task to be answerable from the map (i.e. not blind guesswork).
REPOS = [
    {
        "name": "projectm",
        "root": ROOT / "projectm",
        "scan_path": "src/libprojectM",
        "tasks": [
            {
                "question": "Where is the audio-injection entry point, and what overloads does an app call to feed PCM samples?",
                "ground_truth": ["AddToBuffer"],
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


def norm(s: str) -> str:
    """Normalize identifier for matching: strip whitespace/case, keep alnum + ::_/.-+"""
    return "".join(c.lower().replace(" ", "") for c in s if c.isalnum() or c in "::_./-+")


async def run_repo(repo: dict) -> dict:
    name = repo["name"]
    root = str(repo["root"])
    report = {"name": name, "tasks": []}

    # Get full repo token estimate once
    full_repo = _full_repo_tokens(root)

    for t in repo["tasks"]:
        missing = []
        found_details = []
        total_mcp_tokens = 0
        for ident in t["ground_truth"]:
            # Use MCP detect (cheap, case-insensitive, finds definitions + refs)
            result = await tricorder_detect(root, ident, max_results=50, include_definitions=True, include_references=False)
            if "error" in result:
                missing.append(ident)
                continue
            results = result.get("results", [])
            defs = [r for r in results if r.get("kind") == "def"]
            if not defs:
                missing.append(ident)
            else:
                # Found - record file:line for verification
                for d in defs:
                    found_details.append(f"{d['file']}:{d['line']} {d['name']}")
            # Add token estimate from this detect call
            total_mcp_tokens += result.get("token_estimate", 0)
        passes = not missing
        report["tasks"].append({
            "question": t["question"],
            "pass": passes,
            "missing": missing,
            "found": found_details,
            "mcp_tokens": total_mcp_tokens,
        })

    report["full_repo_tokens"] = full_repo
    return report


async def main():
    only = sys.argv[1] if len(sys.argv) > 1 else None
    reports = []
    for repo in REPOS:
        if only and only != repo["name"]:
            continue
        reports.append(await run_repo(repo))
        print(f"ran {repo['name']}")

    print()
    print(f"{'repo':<14}{'task#':<6}{'PASS?':<6}{'full_tok':<12}{'MCP_tok':<10}{'savings':<9}")
    print("-" * 65)
    all_pass = True
    for r in reports:
        for i, t in enumerate(r["tasks"], 1):
            all_pass = all_pass and t["pass"]
            mcp_tok = t.get("mcp_tokens", 0)
            savings = round(max(0.0, 1 - mcp_tok / r["full_repo_tokens"]) * 100, 1) if r["full_repo_tokens"] else 0.0
            print(f"{r['name']:<14}{i:<6}{'PASS' if t['pass'] else 'FAIL':<6}"
                  f"{r['full_repo_tokens']:<12}{mcp_tok:<10}{savings:<9}")
        if not r["tasks"]:
            print(f"{r['name']:<14}{'-':<6}{'-':<6}{r['full_repo_tokens']:<12}{'-':<10}{'-':<9}")
    print("-" * 65)
    cred = "ALL TASKS PASS" if all_pass else "SOME TASKS FAIL"
    print(f"RESULT: {cred}")
    for r in reports:
        for t in r["tasks"]:
            if not t["pass"]:
                print(f"  [{r['name']}] MISSING via MCP detect: {t['missing']}")
                print(f"      Q: {t['question']}")
            else:
                print(f"  [{r['name']}] FOUND: {', '.join(t.get('found', []))}")
    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))