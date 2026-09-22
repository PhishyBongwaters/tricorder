#!/usr/bin/env python3
"""Swift-repo A/B comparison worker.

Compares tricorder BASELINE (~/workspace/tricorder-base @ 438fd0b, the
fix/parallel-qualify divergence point from dev/db-map) against BRANCH HEAD
(~/workspace/tricorder @ 5316c90) on context tokens per navigation query,
using the swiftlang/swift compiler repo as the corpus.

Method mirrors run_eval_v3.py --rung-via mcp (intended usage):
  - Pre-scan each variant into its OWN DB (--map-tokens 500, optional
    --max-files cap identical for both); scan cost recorded, never charged.
  - Stage each variant's DB at the canonical in-repo location
    <swift>/.tricorder/db/swift.db immediately before that variant's run
    (the MCP server resolves its DB from there; fresh helper process per
    rung, so swapping is safe).
  - Per question: detect(k1) -> symbols(k1) -> detail(best hit) ->
                   detect(k2) -> symbols(k2) -> detail(best hit)
    via tricorder_server MCP tool functions (baseline CLI lacks
    --detect/--symbols, so MCP is the only symmetric surface).
  - Tokens: tiktoken cl100k via utils.count_tokens from the branch-head
    tree, applied identically to both variants' agent-visible text.
  - Calls: true per-rung invocation count.
  - Success: ground-truth file (basename or path suffix) cited anywhere in
    the question's evidence bag AND the cited path exists in the repo.

Sequential runs; no live agent. Report ONLY measured numbers.
"""
import argparse
import json
import shutil
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("--swift-root", default="/home/hatch/workspace/comparisons/swift")
ap.add_argument("--outdir", default=None)
ap.add_argument("--max-files", type=int, default=0,
                help="0 = no cap; else identical --max-files for both scans")
ap.add_argument("--rung-timeout", type=int, default=300)
ap.add_argument("--scan-timeout", type=int, default=2400)
ap.add_argument("--only-prescan", action="store_true",
                help="build both DBs and exit (resilient staging)")
ap.add_argument("--skip-prescan", action="store_true",
                help="reuse existing build DBs, run only the question loops")
ap.add_argument("--paths", nargs="*", default=[],
                help="explicit scan paths (positional CLI paths); when given, "
                     "--max-files does not apply")
args = ap.parse_args()

TIP_ROOT = "/home/hatch/workspace/tricorder"          # branch head 5316c90
BASE_ROOT = "/home/hatch/workspace/tricorder-base"     # baseline 438fd0b
VENV_PY = "/home/hatch/workspace/tricorder-venv/bin/python"
SWIFT = str(Path(args.swift_root).resolve())

sys.path.insert(0, TIP_ROOT)
from utils import count_tokens  # noqa: E402  (one tokenizer, both variants)

MCP_HELPER = [VENV_PY, "/home/hatch/workspace/tricorder-linux-eval/mcp_rung_helper.py"]

QUESTIONS = [
    {
        "id": "Q1-typecheck-call",
        "text": "Where is type checking of function calls implemented?",
        "keywords": ["CSApply", "type check function call"],
        "ground_truth": ["lib/Sema/CSApply.cpp", "lib/Sema/TypeCheckExpr.cpp",
                         "lib/Sema/ConstraintSystem.cpp"],
    },
    {
        "id": "Q2-sil-inliner",
        "text": "How does the SIL optimizer's inliner decide what to inline?",
        "keywords": ["PerformanceInliner", "inline cost model"],
        "ground_truth": ["lib/SILOptimizer/Transforms/PerformanceInliner.cpp",
                         "lib/SILOptimizer/Utils/SILInliner.cpp"],
    },
    {
        "id": "Q3-string-interp",
        "text": "Where is string interpolation desugared in the compiler?",
        "keywords": ["InterpolatedStringLiteral", "string interpolation"],
        "ground_truth": ["lib/Sema/CSGen.cpp", "lib/Sema/CSApply.cpp",
                         "include/swift/AST/Expr.h"],
    },
    {
        "id": "Q4-parse-expr",
        "text": "Where is the Swift expression parser implemented?",
        "keywords": ["parseExpr", "expression parser"],
        "ground_truth": ["lib/Parse/ParseExpr.cpp"],
    },
    {
        "id": "Q5-name-lookup",
        "text": "Where is qualified name lookup implemented?",
        "keywords": ["NameLookup", "qualified name lookup"],
        "ground_truth": ["lib/AST/NameLookup.cpp"],
    },
]

VARIANTS = [("baseline", BASE_ROOT), ("branch", TIP_ROOT)]


def sh(cmd, timeout):
    t0 = time.monotonic()
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return p.returncode, p.stdout, p.stderr, time.monotonic() - t0
    except subprocess.TimeoutExpired:
        return -1, "", "TIMEOUT", time.monotonic() - t0


def tokens(text):
    return count_tokens(text, "gpt-4")


def db_digest_text(db_path):
    try:
        con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        try:
            n = con.execute("SELECT COUNT(*) FROM file_state").fetchone()[0]
            t = con.execute("SELECT COUNT(*) FROM tags").fetchone()[0]
            m = con.execute(
                "SELECT signature FROM meta ORDER BY rowid DESC LIMIT 1"
            ).fetchone()
        finally:
            con.close()
    except Exception:
        return ""
    sig = (m[0][:8] if m and m[0] else "?")
    return (f"mapped: {n} files, {t} tags (db sig {sig}). Retrieve, don't "
            "rescan: mcp_tricorder_detect to locate, mcp_tricorder_symbols "
            "for shape, mcp_tricorder_detail for body+callers.")


def prescan(code_root, db_path):
    cmd = [VENV_PY, str(Path(code_root) / "tricorder.py"),
           "--root", SWIFT, "--map-tokens", "500",
           "--format", "text", "--db-path", str(db_path)]
    if args.max_files:
        cmd += ["--max-files", str(args.max_files)]
    # explicit positional scan paths (relative to --root)
    cmd += args.paths
    return sh(cmd, timeout=args.scan_timeout)


def stage_canonical(db_path):
    canon = Path(SWIFT) / ".tricorder" / "db" / (Path(SWIFT).name + ".db")
    canon.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(db_path, canon)
    return str(canon)


def parse_mcp_hit(visible, key):
    try:
        d = json.loads(visible)
    except Exception:
        return None
    items = d.get(key) or []
    if not items or not isinstance(items, list):
        return None
    h = items[0]
    try:
        return h.get("file"), h.get("name"), str(h.get("line", ""))
    except Exception:
        return None


def run_question(code_root, q):
    steps, seen = [], {}
    tot_tk, calls = 0, 0
    for qi, kw in enumerate(q["keywords"], start=1):
        steps.append((f"detect{qi}", MCP_HELPER + [code_root, "detect", SWIFT, kw]))
        steps.append((f"symbols{qi}", MCP_HELPER + [code_root, "symbols", SWIFT, kw]))
        steps.append((f"detail{qi}", ("MCP_DETAIL", qi)))
    artifacts = []
    for name, spec in steps:
        if isinstance(spec, tuple) and spec[0] == "MCP_DETAIL":
            qi = spec[1]
            hit = parse_mcp_hit(seen.get(f"symbols{qi}", ""), "symbols")
            if hit is None:
                hit = parse_mcp_hit(seen.get(f"detect{qi}", ""), "results")
            if hit and hit[0] and hit[1]:
                f, nm, ln = hit
                cmd = MCP_HELPER + [code_root, "detail", SWIFT, f, nm, ln or "0"]
            else:
                cmd = ["echo", "NO_HIT_FOR_DETAIL"]
        else:
            cmd = spec
        rc, out, err, dt = sh(cmd, timeout=args.rung_timeout)
        visible = out
        tk = tokens(visible)
        artifacts.append({"step": name, "rc": rc, "seconds": round(dt, 2),
                          "tokens": tk, "visible_text": visible})
        seen[name] = visible
        tot_tk += tk
        calls += 1
    evidence = "\n\n".join(f"### {a['step']}\n{a['visible_text']}" for a in artifacts)
    return artifacts, tot_tk, calls, evidence


def grade(evidence, q):
    low = evidence.lower()
    gt_cited = [g for g in q["ground_truth"]
                if g.lower() in low or Path(g).name.lower() in low]
    # verify at least one cited ground-truth file actually exists in the repo
    exists = [g for g in gt_cited if (Path(SWIFT) / g).exists()]
    return {"ground_truth_cited": gt_cited,
            "ground_truth_existing": exists,
            "pass": bool(exists)}


def main():
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    outdir = Path(args.outdir or f"/home/hatch/workspace/comparisons/swift-eval/results-{stamp}")
    outdir.mkdir(parents=True, exist_ok=True)

    file_count = int(subprocess.run(
        ["git", "-C", SWIFT, "ls-files"], capture_output=True, text=True
    ).stdout.count("\n"))

    # verify ground truth files exist before running
    for q in QUESTIONS:
        for g in q["ground_truth"]:
            if not (Path(SWIFT) / g).exists():
                print(f"WARN: ground truth missing: {g}", flush=True)

    builds = {}
    for vname, code_root in VARIANTS:
        db = outdir / f"build_{vname}.db"
        if args.skip_prescan and db.exists():
            builds[vname] = {"db": str(db), "rc": 0, "seconds": -1,
                             "stdout_tokens": -1, "stderr_tail": "(reused)",
                             "digest": db_digest_text(str(db))}
            print(f"prescan {vname}: reused {db}", flush=True)
            continue
        if db.exists():
            db.unlink()  # never resume a partial/interrupted scan
        rc, out, err, dt = prescan(code_root, db)
        builds[vname] = {"db": str(db), "rc": rc, "seconds": round(dt, 2),
                         "stdout_tokens": tokens(out),
                         "stderr_tail": err[-500:] if err else "",
                         "digest": db_digest_text(str(db))}
        print(f"prescan {vname}: rc={rc} {dt:.1f}s", flush=True)

    (outdir / "prescan.json").write_text(json.dumps(builds, indent=1))

    if args.only_prescan:
        print("only-prescan: DBs built, exiting", flush=True)
        return

    if args.skip_prescan:
        prev = json.loads((outdir / "prescan.json").read_text())
        builds = prev

    rows = []
    for q in QUESTIONS:
        for vname, code_root in VARIANTS:
            canon = stage_canonical(builds[vname]["db"])
            t0 = time.monotonic()
            artifacts, tot_tk, calls, evidence = run_question(code_root, q)
            dur = time.monotonic() - t0
            g = grade(evidence, q)
            qdir = outdir / "artifacts" / q["id"] / vname
            qdir.mkdir(parents=True)
            (qdir / "steps.json").write_text(json.dumps(
                [{k: a[k] for k in ("step", "rc", "seconds", "tokens")}
                 for a in artifacts], indent=1))
            (qdir / "evidence.txt").write_text(evidence)
            (qdir / "grade.json").write_text(json.dumps(g, indent=1))
            for a in artifacts:
                (qdir / f"step_{a['step']}.txt").write_text(a["visible_text"])
            rows.append({"question": q["id"], "variant": vname,
                         "tokens": tot_tk, "calls": calls,
                         "duration_s": round(dur, 2), "pass": int(g["pass"]),
                         "gt_existing": ";".join(g["ground_truth_existing"])})
            print(f"{q['id']} {vname}: {tot_tk} tok, {calls} calls, "
                  f"pass={g['pass']} {dur:.1f}s", flush=True)

    # cleanup: remove canonical staged DB from the repo
    canon = Path(SWIFT) / ".tricorder" / "db" / (Path(SWIFT).name + ".db")
    try:
        canon.unlink()
    except OSError:
        pass

    (outdir / "results.csv").write_text(
        "question,variant,tokens,calls,duration_s,pass,gt_existing\n" +
        "\n".join(f"{r['question']},{r['variant']},{r['tokens']},{r['calls']},"
                  f"{r['duration_s']},{r['pass']},{r['gt_existing']}" for r in rows)
        + "\n")

    lines = ["# Swift-repo A/B comparison (method v3-mcp)",
             "",
             f"Date (UTC): {stamp}",
             f"Corpus: swiftlang/swift @ {SWIFT} ({file_count} files via git ls-files)",
             f"Baseline: tricorder-base @ 438fd0b (fix/parallel-qualify divergence from dev/db-map)",
             "Branch: ~/workspace/tricorder @ 5316c90 (fix/parallel-qualify head)",
             f"Rung surface: MCP (tricorder_server detect/symbols/detail); max-files cap: {args.max_files or 'none'}; "
             f"scan paths: {' '.join(args.paths) or '(auto-discovery, whole repo)'}",
             "Tokenizer: tiktoken cl100k (tip utils.count_tokens), identical both sides.",
             "Pre-scan cost is one-time and NEVER charged per question.",
             ""]
    lines.append("## Pre-scan (sunk, one-time, not charged)")
    for vname, _ in VARIANTS:
        b = builds[vname]
        dtext = db_digest_text(b["db"])
        lines.append(f"- {vname}: rc={b['rc']}, {b['seconds']}s, map stdout "
                     f"{b['stdout_tokens']} tok; digest: {dtext}"
                     + (f" STDERR: {b['stderr_tail']}" if b["rc"] != 0 else ""))
    lines += ["", "## Per-question detail",
              "| Question | Baseline tokens | Branch tokens | Baseline calls | Branch calls | Baseline pass | Branch pass |"]
    for q in QUESTIONS:
        rb = next(r for r in rows if r["question"] == q["id"] and r["variant"] == "baseline")
        rt = next(r for r in rows if r["question"] == q["id"] and r["variant"] == "branch")
        lines.append(f"| {q['id']}: {q['text']} | {rb['tokens']} | {rt['tokens']} | "
                     f"{rb['calls']} | {rt['calls']} | "
                     f"{'PASS' if rb['pass'] else 'FAIL'} | {'PASS' if rt['pass'] else 'FAIL'} |")
    tb = sum(r["tokens"] for r in rows if r["variant"] == "baseline")
    tt = sum(r["tokens"] for r in rows if r["variant"] == "branch")
    cb = sum(r["calls"] for r in rows if r["variant"] == "baseline")
    ct = sum(r["calls"] for r in rows if r["variant"] == "branch")
    pb = sum(r["pass"] for r in rows if r["variant"] == "baseline")
    pt = sum(r["pass"] for r in rows if r["variant"] == "branch")
    lines += ["", "## Totals",
              f"- Tokens: baseline {tb}, branch {tt} (delta {tt - tb:+d})",
              f"- Calls: baseline {cb}, branch {ct}",
              f"- Pass: baseline {pb}/{len(QUESTIONS)}, branch {pt}/{len(QUESTIONS)}"]
    (outdir / "results.md").write_text("\n".join(lines) + "\n")
    print(str(outdir), flush=True)


if __name__ == "__main__":
    main()
