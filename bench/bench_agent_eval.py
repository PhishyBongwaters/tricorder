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
import json
import os
import re
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(r"D:\Projects")
TESTBED = ROOT / "Tricorder-Testing-Repos"
STATE_DB = Path(os.environ["LOCALAPPDATA"]) / "hermes" / "state.db"
LOG_PATH = Path(os.environ["LOCALAPPDATA"]) / "hermes" / "logs" / "agent.log"
BENCH_BASELINE_LOG = (Path(os.environ["LOCALAPPDATA"]) / "hermes"
                      / "profiles" / "bench-baseline" / "logs" / "agent.log")
BENCH_BASELINE_DB = (Path(os.environ["LOCALAPPDATA"]) / "hermes"
                     / "profiles" / "bench-baseline" / "state.db")
# Variant A's agent subprocess runs on bench-tricorder (separate profile that
# already has the tricorder plugin configured). Keeps A's session row out of
# the user's default profile — the same isolation judge already gets from
# bench-baseline. ponytail: reuse existing profile, don't add.
BENCH_TRICORDER_LOG = (Path(os.environ["LOCALAPPDATA"]) / "hermes"
                       / "profiles" / "bench-tricorder" / "logs" / "agent.log")
BENCH_TRICORDER_DB = (Path(os.environ["LOCALAPPDATA"]) / "hermes"
                      / "profiles" / "bench-tricorder" / "state.db")
# Judge runs on the bench-baseline profile too — it's a separate hermes chat
# subprocess and we don't want it writing its session row into the user's
# default profile. bench-baseline is plugin-clean and already exists, so
# reusing it avoids creating yet another profile. ponytail: reuse, don't add.
BENCH_JUDGE_PROFILE = "bench-baseline"
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
                    "projectM's PCM audio pipeline feeds multiple renderer backends. "
                    "Without opening every file, explain how PCM::AddToBuffer's overloads "
                    "are dispatched to those backends and trace the path where loudness-band "
                    "computation intersects with the active renderer — naming the dispatch "
                    "entry and the per-frame callback the renderers pull from."
                ),
                "ground_truth": [
                    "src/libprojectM/Audio/PCM.cpp",
                    "src/libprojectM/Audio/PCM.hpp",
                ],
                "rubric": (
                    "Must name PCM::AddToBuffer's renderer-dispatch overload, "
                    "the per-frame pull callback (PCM::GetNewMatrixFrame or alias), "
                    "and the point where Loudness band computation feeds the active renderer. "
                    "A bare grep of AddToBuffer signatures without the dispatch path fails."
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

    variant='A' -> tricorder MCP enabled (bench-tricorder profile).
    variant='B' -> baseline tools only (bench-baseline profile).
    model/provider -> pinned on both legs so A/B is a clean comparison.
    """
    workdir = repo_task["path"]
    prompt = repo_task["question"]
    # Variant A MUST use the tricorder MCP tools — relying on the skill text
    # alone let the model fall back to blind grep/file reads (the run showed
    # zero mcp__tricorder__ calls). Force it in the prompt so the harness's
    # honesty gate (count_tricorder_calls) actually measures a tricorder leg.
    if variant == "A":
        prompt = (
            f"CRITICAL DIRECTIVE: Use the codebase-tricorder tools for symbol search and inspection. "
            f"Pass project_root=\"{workdir}\" to any mcp__tricorder__* tool calls. "
            f"Question: " + prompt
        )
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
    if variant == "A":
        cmd += ["-s", "codebase-tricorder"]
        cmd += ["--profile", "bench-tricorder"]
    elif variant == "B":
        cmd += ["--profile", "bench-baseline"]
    print(f"[{variant}] running: {' '.join(cmd)}")
    env = os.environ.copy()
    r = subprocess.run(cmd, capture_output=True, text=True, env=env)
    # hermes chat (non-interactive) doesn't print the session id to stdout, so
    # recover the newest CLI session from the right profile's agent.log.
    # CRITICAL: variant subprocesses use their profile's own log, NOT the
    # default log. Reading the default log for A would grab the user's real
    # chat session (sid-collision bug that made A reports point at the wrong
    # session). A -> bench-tricorder, B -> bench-baseline. ponytail: dict
    # over if/elif.
    PROFILE_LOG = {"A": BENCH_TRICORDER_LOG, "B": BENCH_BASELINE_LOG}
    log_path = PROFILE_LOG.get(variant, LOG_PATH)
    sid = recover_latest_session_id(log_path, marker=repr(prompt)[:80])
    report_a = track_report(sid, variant) if sid else None
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


def track_report(sid, variant="A"):
    """Run track_session.py --save on a session id; return saved report path.

    The report filename gets "-A"/"-B" appended so A and B reports don't
    collide even if the recovered session id happens to be identical.

    Variant B's session lives in the bench-baseline profile's own state.db and
    agent.log, so we pass --db / --log pointing there. (Reading the default
    profile's DB for B caused "session not found" — third bench bug.)
    """
    if not sid or not TRACK_SCRIPT.exists():
        return None
    out = OUTPUT_DIR / f"report_{sid}-{variant}.md"
    cmd = [sys.executable, str(TRACK_SCRIPT), "--save", str(out), sid]
    # Same isolation: A reads bench-tricorder's state.db, B reads
    # bench-baseline's. Without this, track_session.py read the default
    # profile's DB and reported "session not found" for both legs. ponytail:
    # same dict as PROFILE_LOG — keep them in sync.
    PROFILE_DB = {"A": BENCH_TRICORDER_DB, "B": BENCH_BASELINE_DB}
    PROFILE_LOG = {"A": BENCH_TRICORDER_LOG, "B": BENCH_BASELINE_LOG}
    if variant in PROFILE_DB:
        cmd += ["--db", str(PROFILE_DB[variant]),
                "--log", str(PROFILE_LOG[variant])]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(f"  [track_report {variant}] WARN: {r.stderr.strip()[:200]}")
    return str(out) if r.returncode == 0 else None


def count_tricorder_calls(report_path):
    """Return number of mcp__tricorder__ tool calls recorded in a report.

    Honesty gate: if Variant A used zero tricorder calls, the A/B comparison
    is NOT a tricorder-vs-baseline result — it's just the model's free choice.
    Counting this prevents fake 'tricorder wins' claims from a run where A
    never exercised the tool.
    """
    if not report_path or not Path(report_path).exists():
        return None
    txt = Path(report_path).read_text(encoding="utf-8", errors="ignore")
    return txt.count("mcp__tricorder__")


def grade_answer(report_path, ground_truth, rubric, model, provider,
                 sid=None, variant="A"):
    """Grade an agent's session against the rubric. Returns (passed, rationale).

    Source of truth is the profile's state.db, not the telemetry report
    (the report only contains tool-call traces, not the agent's prose answer).

    Grades the agent's FINAL assistant message only — never the tool-result
    dump. Catching ground_truth tokens in a tool's output proves the agent
    SAW the answer, not that it ANSWERED. To pass, the agent must write the
    identifiers in its own words in its own message.

    Fast path: string-match ground_truth against the last assistant message
    in state.db, with hierarchical fallback (full path -> last 2 components
    -> basename). Cheap, no model call.

    Slow path: if string match fails (or no final answer exists), invoke a
    higher-reasoning model via `hermes chat --cli` with the final answer +
    rubric and parse {"passed": bool, "rationale": str} from its output.

    Rationale prefixes indicate which path ran: "PASS:" / "SEMANTIC PASS:" /
    "FAIL:" / "no final answer:" / "Judge Error:".
    """
    # Caller already has the sid and variant; use them, don't re-parse the
    # filename (the old regex+string-sniff was filename archaeology).
    if not sid:
        return False, "no sid provided"
    # Same dict as track_report — variant's session lives in the variant's
    # own profile DB. Reading STATE_DB (the user's default) for A returns
    # zero rows because A's session is in BENCH_TRICORDER_DB now. The old
    # code only had B routed correctly; A was implicit. ponytail: one dict.
    PROFILE_DB = {"A": BENCH_TRICORDER_DB, "B": BENCH_BASELINE_DB}
    db_path = PROFILE_DB.get(variant, STATE_DB)
    if not db_path.exists():
        return False, f"no db at {db_path}"
    try:
        final_answer = None
        for cand in dict.fromkeys((db_path, STATE_DB)):  # dedupe; STATE_DB fallback for pre-isolation reports
            if not cand.exists():
                continue
            con = sqlite3.connect(str(cand))
            cur = con.cursor()
            cur.execute(
                "SELECT content FROM messages WHERE session_id = ? "
                "AND role = 'assistant' AND content IS NOT NULL AND content != '' "
                "ORDER BY id DESC LIMIT 1",
                (sid,),
            )
            row = cur.fetchone()
            con.close()
            if row and row[0]:
                final_answer = row[0]
                break
    except Exception as e:
        return False, f"db error: {e}"

    if not final_answer:
        return False, "no final answer: agent produced no assistant message"
    final_lower = final_answer.lower()

    # Fast path: hierarchical ground_truth match against the FINAL ANSWER only.
    # The agent must name the identifier itself; finding it inside a tool
    # result it read doesn't count.
    found = []
    for g in ground_truth:
        gl = g.lower()
        if "/" in gl:
            parts = gl.split("/")
            cands = [gl, "/".join(parts[-2:]), parts[-1]]
        else:
            cands = [gl]
        if any(c in final_lower for c in cands):
            found.append(g)
    if ground_truth and len(found) == len(ground_truth):
        return True, f"PASS: final answer names {len(found)}/{len(ground_truth)} ground_truth"

    # Slow path: semantic LLM judge. Cap the final answer to keep the
    # judge's context window sane.
    judge_prompt = f"""You are a Pragmatic Technical Auditor. Verify whether an AI agent's final answer satisfies a rubric.

RULES:
- BE SEMANTIC: If the agent uses different but correct terminology, or slightly different file paths (e.g., ./file.py vs file.py), it is a PASS.
- BE PRAGMATIC: Do not fail for minor formatting or style issues.
- FOCUS ON INTENT: Does the agent's response satisfy the core requirements of the rubric? If yes, it is a PASS.
- FAIL ONLY IF: The agent is factually wrong, misses a core requirement, or hallucinates information not present in the repo context.

OUTPUT FORMAT (JSON only, no markdown fences):
{{"passed": <true|false>, "rationale": "<one sentence explanation>"}}

RUBRIC:
{rubric}

GROUND TRUTH (expected files/symbols the answer should reference):
{', '.join(ground_truth)}

AGENT'S FINAL ANSWER (the last assistant message in the session — this is all you grade; ignore tool outputs):
{final_answer[:15000]}
"""
    qf = tempfile.NamedTemporaryFile(
        "w", suffix=".txt", delete=False, encoding="utf-8"
    )
    qf.write(judge_prompt)
    qf.close()
    try:
        r = subprocess.run(
            ["hermes", "chat", "--query-file", qf.name, "--cli",
             "-m", model, "--provider", provider, "--max-turns", "1",
             "--profile", BENCH_JUDGE_PROFILE],
            capture_output=True, text=True, timeout=180,
        )
        out = (r.stdout or "").strip()
        # hermes chat echoes the query (incl. a {"passed":...} TEMPLATE
        # example near the top) and wraps output in ANSI. The model's real
        # verdict is the LAST balanced JSON object. Strip fences + ANSI,
        # then walk candidate '{' positions from the right and let
        # json.JSONDecoder.raw_decode decide where the object actually ends
        # (it handles string escapes correctly, unlike a brace counter).
        # ponytail: stdlib JSONDecoder handles escape edge cases a
        # naive brace-counter gets wrong.
        out = out.replace("```json", "").replace("```", "")
        out = re.sub(r"\x1b\[[0-9;]*m", "", out)
        decoder = json.JSONDecoder()
        obj = None
        idx = len(out) - 1
        while idx >= 0:
            i = out.rfind("{", 0, idx + 1)
            if i < 0:
                break
            try:
                candidate, _end = decoder.raw_decode(out[i:])
                obj = candidate
                break
            except json.JSONDecodeError:
                idx = i - 1
        if obj is None:
            raise ValueError("no JSON verdict in judge output")
        decision = obj
        passed = bool(decision.get("passed"))
        rationale = str(decision.get("rationale", ""))
        prefix = "SEMANTIC PASS" if passed else "SEMANTIC FAIL"
        return passed, f"{prefix}: {rationale}"
    except Exception as e:
        return False, f"Judge Error: {e}"
    finally:
        try:
            os.unlink(qf.name)
        except OSError:
            pass


def main():
    p = argparse.ArgumentParser()
    p.add_argument("repo", nargs="?", default=None)
    p.add_argument("--variant", choices=["A", "B", "both"], default="both")
    p.add_argument("--model", default="hy3-free",
                   help="Model pinned on BOTH variants (default: hy3-free).")
    p.add_argument("--provider", default="opencode-free",
                   help="Provider pinned on BOTH variants (default: opencode-free).")
    p.add_argument("--judge", action="store_true",
                   help="Run the LLM judge on each leg's final answer. "
                        "Off by default — telemetry-only runs are fast and "
                        "free. ponytail: opt-in, no surprises.")
    p.add_argument("--judge-model", default=None,
                   help="Model for the judge (default: same as --model).")
    p.add_argument("--judge-provider", default=None,
                   help="Provider for the judge (default: same as --provider).")
    p.add_argument("--judge-only", action="store_true",
                   help="Re-grade EXISTING on-disk reports without re-running "
                        "the agent. Needs --variant and the report file(s); "
                        "reads session id from the report filename. ponytail: "
                        "re-grade, don't re-run (kills LLM variance).")
    args = p.parse_args()

    OUTPUT_DIR.mkdir(exist_ok=True)

    tasks = [t for t in TASKS if not args.repo or t["repo"] == args.repo]
    if not tasks:
        print("no tasks matched"); return 1

    for task in tasks:
        print(f"\n=== {task['repo']} ===")
        jm = args.judge_model or args.model
        jp = args.judge_provider or args.provider

        # --judge-only: re-grade existing on-disk reports for this repo+variant.
        # Report filenames encode {sid}-{variant}; the task's ground_truth/
        # rubric come from the repo-matched task. No agent subprocess runs, so
        # no LLM variance and no polluting a fresh session. ponytail: one glob.
        if args.judge_only:
            out = []
            for v in ("A", "B"):
                if args.variant not in (v, "both"):
                    continue
                for rp in sorted(
                    OUTPUT_DIR.glob(f"report_*-{v}.md"),
                    key=lambda p: p.stat().st_mtime,
                    reverse=True,
                ):
                    # Report filenames don't embed the repo, so only grade
                    # reports whose Title references THIS task's question
                    # (telemetry bodies never contain ground_truth paths).
                    # Match >=2 overlapping alpha words — robust to how titles
                    # are auto-summarized. "what handler processes admin" vs
                    # title "identify admin invites handler claim validation"
                    # shares {handler, admin} >= 2. A projectm report title
                    # won't. ponytail: token overlap, no schema.
                    body = rp.read_text(encoding="utf-8", errors="ignore")
                    m = re.search(r"\*\*Title:\*\*\s*(.+)", body)
                    title = m.group(1).lower() if m else ""
                    q_words = {w for w in task["question"].lower().split()
                               if w.isalpha()}
                    title_words = set(title.split())
                    shared = q_words & title_words
                    if len(shared) < 2:
                        continue
                    sid = rp.stem.replace(f"-{v}", "").replace("report_", "")
                    passed, rationale = grade_answer(
                        str(rp), task.get("ground_truth", []),
                        task.get("rubric", ""), jm, jp,
                        sid=sid, variant=v,
                    )
                    out.append(rp.name)
                    print(f"  [{v}] {rp.name} GRADE="
                          f"{'PASS' if passed else 'FAIL'} -- {rationale}")
            if not out:
                print(f"  no on-disk reports for repo={task['repo']} "
                      f"variant={args.variant}")
            print(f"  VERDICT: JUDGE-ONLY (re-graded {len(out)} report(s))")
            continue

        results = []
        if args.variant in ("A", "both"):
            results.append(run_variant(task, "A", args.model, args.provider))
        if args.variant in ("B", "both"):
            results.append(run_variant(task, "B", args.model, args.provider))
        # Summarize which session ids + reports landed, with a tricorder-usage
        # honesty gate so a no-tricorder A leg is flagged, not silently scored.
        grades = {}
        tc_by_variant = {}
        # Judge model/provider default to the agent's — same reproducibility
        # by default, opt-in to a stronger model for grading.
        jm = args.judge_model or args.model
        jp = args.judge_provider or args.provider
        for r in results:
            tc = count_tricorder_calls(r.get("report"))
            tc_by_variant[r["variant"]] = tc
            if args.judge:
                # Root-cause guard: a missing sid means the agent subprocess
                # never wrote a session row. Don't pretend it's a FAIL —
                # surface it as a WARN and skip grading.
                if not r.get("session_id"):
                    print(f"  [{r['variant']}] WARN: no session_id recovered "
                          f"(rc={r['rc']}); skipping grade. "
                          f"stderr: {(r.get('stderr') or '')[:200]}")
                else:
                    # Source of truth is state.db, not the report.
                    # Pass sid+variant straight in (no filename re-parsing).
                    passed, rationale = grade_answer(
                        r.get("report"),
                        task.get("ground_truth", []),
                        task.get("rubric", ""),
                        jm, jp,
                        sid=r["session_id"], variant=r["variant"],
                    )
                    grades[r["variant"]] = (passed, rationale)
                    print(f"  [{r['variant']}] GRADE="
                          f"{'PASS' if passed else 'FAIL'} -- {rationale}")
            if r["variant"] == "A":
                flag = (f"tricorder_calls={tc}"
                        if tc is not None else "report=MISSING")
                if tc == 0:
                    flag += "  <<< A did NOT use tricorder: this leg is NOT a "
                    flag += "tricorder-vs-baseline result (model chose other tools)"
            else:
                flag = (f"tricorder_calls={tc} (must be 0 for clean control)"
                        if tc is not None else "report=MISSING")
            print(f"  [{r['variant']}] sid={r.get('session_id')} "
                  f"rc={r['rc']} {flag}")
        # VERDICT: only a real A/B if A used tricorder AND both legs graded.
        # With --judge off, grades is empty → telemetry-only verdict.
        a_tc = tc_by_variant.get("A")
        
        # Read billed input tokens from saved reports for direct comparison
        tok_a, tok_b = None, None
        for r in results:
            rep = r.get("report")
            if rep and Path(rep).exists():
                txt = Path(rep).read_text(encoding="utf-8", errors="ignore")
                m = re.search(r'- Input tokens:\s*([\d,]+)', txt)
                if m:
                    val = int(m.group(1).replace(",", ""))
                    if r["variant"] == "A":
                        tok_a = val
                    else:
                        tok_b = val

        if tok_a is not None and tok_b is not None:
            diff = tok_a - tok_b
            pct = (diff / tok_b) * 100 if tok_b else 0
            print(f"  [TOKENS] A={tok_a:,} | B={tok_b:,} | Δ={diff:+,} ({pct:+.1f}%)")

        if not args.judge:
            print(f"  VERDICT: TELEMETRY ONLY (--judge off; "
                  f"a_tc={a_tc})")
        elif a_tc and a_tc > 0 and "A" in grades and "B" in grades:
            a_pass, _ = grades["A"]
            b_pass, _ = grades["B"]
            print(f"  VERDICT: VALID A/B | A={'PASS' if a_pass else 'FAIL'} "
                  f"B={'PASS' if b_pass else 'FAIL'}")
        else:
            print(f"  VERDICT: NOT a valid A/B "
                  f"(a_tc={a_tc}, grades={list(grades.keys())})")

    print("\nDone. Reports saved under", OUTPUT_DIR)


if __name__ == "__main__":
    main()
