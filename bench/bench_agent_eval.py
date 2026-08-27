#!/usr/bin/env python3
"""
bench_agent_eval.py — Real A/B benchmark harness for issue #44.

Runs Variant A (Tricorder MCP enabled, escalating rung-by-rung) vs
Variant B (baseline tools only — no tricorder MCP) on the SAME relationship
tasks, and captures real session telemetry via track_session.py.

Usage:
  python bench_agent_eval.py                 # all repos/tasks
  python bench_agent_eval.py projectm        # one repo
  python bench_agent_eval.py --variant only  # A or B (debug)

Honest A/B rules (per issue #44 plan v4):
- Same task, same model, same prompt to both variants.
- Variant A: tricorder MCP enabled; agent must escalate T0 -> detect ->
  symbols -> detail -> full-file (no pre-injected T1 map).
- Variant B: baseline tools only (file_search, read_file, grep, terminal).
- Metrics from real session state.db + agent.log via track_session.py.
"""
import argparse
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(r"D:\Projects")
TESTBED = ROOT / "Tricorder-Testing-Repos"
STATE_DB = Path(os.environ["LOCALAPPDATA"]) / "hermes" / "state.db"
LOG_PATH = Path(os.environ["LOCALAPPDATA"]) / "hermes" / "logs" / "agent.log"
TRACK_SCRIPT = Path(__file__).parent / "track_session.py"  # bench-local copy
OUTPUT_DIR = ROOT / "tricorder-test-reports"


# ---------------------------------------------------------------------------
# Task corpus — structural/relationship questions, rubric-graded (not grep bait)
# Each task has distinct answers where Tricorder's caller/callee map should cut
# tool calls and irrelevant reads vs blind grep.
# ---------------------------------------------------------------------------
TASKS = [
    {
        "repo": "projectm",
        "path": str(ROOT / "projectm"),
        "scan_path": "src/libprojectM",
        "question": (
            "Trace the call chain from PCM::AddToBuffer through the renderer "
            "overloads it dispatches, and identify where loudness band "
            "computation hooks into that chain."
        ),
        "ground_truth": [
            "src/libprojectM/Audio/PCM.cpp",
            "src/libprojectM/Audio/PCM.hpp",
        ],
        "rubric": (
            "Must name the PCM::AddToBuffer overloads and the Loudness band "
            "computation path."
        ),
    },
    {
        "repo": "vaultwarden",
        "path": str(TESTBED / "vaultwarden"),
        "scan_path": "src",
        "question": (
            "What handler processes admin invites, and how does it validate "
            "claims against the database connection layer?"
        ),
        "ground_truth": [
            "src/api/admin.rs",
            "src/auth.rs",
        ],
        "rubric": (
            "Must reference generate_invite / admin_page and the DbConn binding."
        ),
    },
    {
        "repo": "go",
        "path": str(TESTBED / "go"),
        "scan_path": "src/cmp",
        "question": (
            "In the cmp package, what ordered-comparison primitives are exposed "
            "and which one Compare delegates to for the Or-shorthand?"
        ),
        "ground_truth": ["src/cmp/cmp.go"],
        "rubric": "Must name Compare, Less, Or and the Ordered constraint.",
    },
    {
        "repo": "kotlin",
        "path": str(TESTBED / "kotlin"),
        "scan_path": "core/compiler.common",
        "question": (
            "How is variance computed for an inline class's expanded type, and "
            "which backend-context method resolves the underlying type?"
        ),
        "ground_truth": [
            "compiler.common.jvm/src/org/jetbrains/kotlin/types/expandedTypeUtils.kt",
        ],
        "rubric": "Must name computeExpandedTypeForInlineClass and getSubstitutedUnderlyingType.",
    },
    {
        "repo": "rails",
        "path": str(TESTBED / "rails"),
        "scan_path": "activerecord/lib/active_record/associations",
        "question": (
            "When you declare a belongs_to association, trace the reflection "
            "chain from the DSL down to foreign_key validation."
        ),
        "ground_truth": ["belongs_to"],
        "rubric": "Must name BelongsToAssociation / BelongsToReflection and foreign_key inference.",
    },
    {
        "repo": "vue",
        "path": str(TESTBED / "vue"),
        "scan_path": "src/v3/reactivity",
        "question": (
            "Implement ref() is defined across overloads — which file holds the "
            "core reactive getter and how does UnwrapRef resolve nested refs?"
        ),
        "ground_truth": ["src/v3/reactivity/ref.ts"],
        "rubric": "Must name effect / trackRefValue and UnwrapRef lazy unwrapping.",
    },
    {
        "repo": "bitburner",
        "path": str(TESTBED / "bitburner-src"),
        "scan_path": "src",
        "question": (
            "Trace the command registration path: how does addAlias feed into "
            "terminal command dispatch, and what loads existing aliases at save load?"
        ),
        "ground_truth": ["src/Alias.ts"],
        "rubric": "Must name loadAliases, addAlias, and the Terminal UI integration.",
    },
    # linux kernel: relationship task, but kept narrow (sched). Tricorder's
    # --pre-index pick_next_task scopes to kernel/sched/* so the 70k-file tree
    # never gets walked blind.
    {
        "repo": "linux",
        "path": str(TESTBED / "linux"),
        "scan_path": ".",
        "pre_index": "pick_next_task",
        "question": (
            "Where is the scheduler entry point that selects which task to run "
            "next, and what per-entity budget helper keeps fair-class tasks current?"
        ),
        "ground_truth": ["kernel/sched"],
        "rubric": "Must name pick_next_task, schedule, update_curr.",
    },
]


def get_session_id_from_log(marker: str):
    """Pull the latest session id matching a marker from agent.log."""
    if not LOG_PATH.exists():
        return None
    needle = f"[{marker}"  # sessions are bracketed like [20260814_124324_a1b2c3]
    with LOG_PATH.open("r", encoding="utf-8", errors="ignore") as f:
        for line in reversed(f.readlines()):
            if marker in line and "[" in line:
                # extract [YYYYMMDD_HHMMSS_xxxxxx]
                idx = line.find("[")
                if idx != -1:
                    end = line.find("]", idx)
                    if end != -1:
                        return line[idx + 1:end]
    return None


def run_variant(repo_task, variant: str, model: str, provider: str):
    """Run one live hermes chat with the given variant, return session id.

    variant='A' -> tricorder MCP enabled (default profile).
    variant='B' -> baseline tools only (tricorder disabled for this run).
    model/provider -> pinned on both legs so A/B is a clean comparison.
    """
    workdir = repo_task["path"]
    prompt = repo_task["question"]
    # Write prompt to a query file so shell quoting never mangles it.
    qf = tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False,
                                     encoding="utf-8")
    qf.write(prompt)
    qf.close()

    usage_file = tempfile.NamedTemporaryFile(suffix=".json", delete=False).name

    cmd = [
        "hermes", "--usage-file", usage_file,
        "chat",
        "--query-file", qf.name,
        "--in", workdir,
        "--max-turns", "60",
        "--run-budget", "120",
        "-m", model,
        "--provider", provider,
        "--cli",
    ]
    if variant == "B":
        # Baseline: --ignore-user-config drops plugins.enabled:[tricorder] from
        # config.yaml, so only builtin tools (read_file, search_files, terminal)
        # load. Model is still pinned via CLI above, so the run stays usable.
        # ponytail: no per-run mcp toggle exists; this avoids mutating the live
        # default profile (which other sessions share).
        cmd += ["--ignore-user-config"]
    print(f"[{variant}] running: {' '.join(cmd)}")
    env = os.environ.copy()
    r = subprocess.run(cmd, capture_output=True, text=True, env=env)
    # hermes chat (non-interactive) doesn't print the session id to stdout, so
    # recover the newest CLI session from agent.log. Each `hermes chat` run
    # logs a turn with format "... session=YYYYMMDD_HHMMSS_xxxxxx ...".
    sid = recover_latest_session_id(LOG_PATH, marker=repr(prompt)[:80])
    report_a = track_report(sid) if sid else None
    return {
        "variant": variant,
        "session_id": sid,
        "session_file": usage_file,
        "stdout": r.stdout,
        "stderr": r.stderr,
        "rc": r.returncode,
        "report": report_a,
    }


def recover_latest_session_id(log_path, marker=None):
    """Return the newest [YYYYMMDD_HHMMSS_xxxxxx] block from agent.log.

    If `marker` is given, restrict to lines containing it (so we don't grab a
    concurrent session started by someone else). Falls back to the absolute
    newest session id in the log tail when marker matches nothing.
    """
    if not log_path.exists():
        return None
    pat = re.compile(r'\[([0-9]{8}_[0-9]{6}_[a-f0-9]+)\]')
    with log_path.open("r", encoding="utf-8", errors="ignore") as f:
        lines = f.readlines()
    # Walk newest-first looking for a session= line (the definitive spawn marker).
    for line in reversed(lines):
        if "session=" in line or "agent.turn_context: conversation turn:" in line:
            m = pat.search(line)
            if m and (marker is None or marker in line):
                return m.group(1)
    # Fallback: any bracketed session id in the tail.
    for line in reversed(lines):
        m = pat.search(line)
        if m:
            return m.group(1)
    return None


def track_report(sid):
    """Run track_session.py --save on a session id; return saved report path."""
    if not sid or not TRACK_SCRIPT.exists():
        return None
    out = OUTPUT_DIR / f"report_{sid}.md"
    r = subprocess.run([sys.executable, str(TRACK_SCRIPT),
                        "--save", str(out), sid],
                       capture_output=True, text=True)
    return str(out) if r.returncode == 0 else None


def main():
    p = argparse.ArgumentParser()
    p.add_argument("repo", nargs="?", default=None)
    p.add_argument("--variant", choices=["A", "B", "both"], default="both")
    p.add_argument("--model", default="hy3-free",
                   help="Model pinned on BOTH variants (default: hy3-free).")
    p.add_argument("--provider", default="opencode-free",
                   help="Provider pinned on BOTH variants (default: opencode-free).")
    args = p.parse_args()

    OUTPUT_DIR.mkdir(exist_ok=True)

    tasks = [t for t in TASKS if not args.repo or t["repo"] == args.repo]
    if not tasks:
        print("no tasks matched"); return 1

    for task in tasks:
        print(f"\n=== {task['repo']} ===")
        results = []
        if args.variant in ("A", "both"):
            results.append(run_variant(task, "A", args.model, args.provider))
        if args.variant in ("B", "both"):
            results.append(run_variant(task, "B", args.model, args.provider))
        # Summarize which session ids + reports landed.
        for r in results:
            print(f"  [{r['variant']}] sid={r.get('session_id')} "
                  f"rc={r['rc']} report={r.get('report') or '(none)'}")

    print("\nDone. Reports saved under", OUTPUT_DIR)


if __name__ == "__main__":
    main()
