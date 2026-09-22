#!/usr/bin/env python3
"""Swift A/B scorer (branch tip vs frozen baseline), 2-rung detect method.

Mirrors eval/comparison-runs/2026-09-21 methodology: prescan each variant
into its own DB (scan paths lib+include, --map-tokens 500, cost sunk), stage
the DB at the canonical cache location before that variant's questions
(fresh helper process per rung, so swapping is safe), then per question
2x detect(keyword, pre_index=keyword). Tokens via tiktoken cl100k through
tip utils.count_tokens, identical both sides. Grading identical to 9/21.
"""
import argparse
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent

ap = argparse.ArgumentParser()
ap.add_argument("--swift-root", required=True)
ap.add_argument("--tip-root", required=True)
ap.add_argument("--base-root", required=True)
ap.add_argument("--outdir", required=True)
ap.add_argument("--only", default=None, help="single question id")
ap.add_argument("--arms", default="both", choices=["both", "branch"])
ap.add_argument("--skip-prescan", action="store_true")
ap.add_argument("--rung-timeout", type=int, default=300)
ap.add_argument("--scan-timeout", type=int, default=2400)
args = ap.parse_args()

SWIFT = str(Path(args.swift_root).resolve())
TIP = args.tip_root
BASE = args.base_root
OUT = Path(args.outdir)
OUT.mkdir(parents=True, exist_ok=True)
HELPER = [sys.executable, str(HERE / "mcp_helper.py")]

sys.path.insert(0, TIP)
from utils import count_tokens  # noqa: E402 (one tokenizer, both variants)

QUESTIONS = [
    {"id": "Q1-typecheck-call", "text": "Where is type checking of function calls implemented?",
     "keywords": ["CSApply", "type check function call"],
     "ground_truth": ["lib/Sema/CSApply.cpp", "lib/Sema/TypeCheckExpr.cpp",
                      "lib/Sema/ConstraintSystem.cpp"]},
    {"id": "Q2-sil-inliner", "text": "How does the SIL optimizer's inliner decide what to inline?",
     "keywords": ["PerformanceInliner", "inline cost model"],
     "ground_truth": ["lib/SILOptimizer/Transforms/PerformanceInliner.cpp",
                      "lib/SILOptimizer/Utils/SILInliner.cpp"]},
    {"id": "Q3-string-interp", "text": "Where is string interpolation desugared in the compiler?",
     "keywords": ["InterpolatedStringLiteral", "string interpolation"],
     "ground_truth": ["lib/Sema/CSGen.cpp", "lib/Sema/CSApply.cpp",
                      "include/swift/AST/Expr.h"]},
    {"id": "Q4-parse-expr", "text": "Where is the Swift expression parser implemented?",
     "keywords": ["parseExpr", "expression parser"],
     "ground_truth": ["lib/Parse/ParseExpr.cpp"]},
    {"id": "Q5-name-lookup", "text": "Where is qualified name lookup implemented?",
     "keywords": ["NameLookup", "qualified name lookup"],
     "ground_truth": ["lib/AST/NameLookup.cpp"]},
]

VARIANTS = [("baseline", BASE), ("branch", TIP)]
if args.arms == "branch":
    VARIANTS = [("branch", TIP)]
QS = [q for q in QUESTIONS if args.only is None or q["id"] == args.only]


def sh(cmd, timeout, env=None):
    t0 = time.monotonic()
    try:
        p = subprocess.run(cmd, capture_output=True, text=True,
                           timeout=timeout, env=env)
        return p.returncode, p.stdout, p.stderr, time.monotonic() - t0
    except subprocess.TimeoutExpired:
        return -1, "", "TIMEOUT", time.monotonic() - t0


def tokens(text):
    return count_tokens(text, "gpt-4")


def db_digest(db_path):
    try:
        con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        try:
            n = con.execute("SELECT COUNT(*) FROM file_state").fetchone()[0]
            t = con.execute("SELECT COUNT(*) FROM tags").fetchone()[0]
        finally:
            con.close()
    except Exception:
        return ""
    return f"mapped: {n} files, {t} tags"


def prescan(code_root, db_path):
    cmd = [sys.executable, str(Path(code_root) / "tricorder.py"),
           "--root", SWIFT, "--map-tokens", "500",
           "--format", "text", "--db-path", str(db_path),
           "lib", "include"]
    return sh(cmd, timeout=args.scan_timeout)


def stage_canonical(vname, db_path):
    cache = OUT / f"cache_{vname}"
    dbdir = cache / "db"
    dbdir.mkdir(parents=True, exist_ok=True)
    dest = dbdir / (Path(SWIFT).name + ".db")
    shutil.copyfile(db_path, dest)
    env = dict(os.environ)
    env["TRICORDER_CACHE_HOME"] = str(cache)
    return env


def run_question(code_root, cache_env, q):
    arts = []
    tot = 0
    for i, kw in enumerate(q["keywords"], start=1):
        cmd = HELPER + [code_root, "detect", SWIFT, kw]
        rc, out, err, dt = sh(cmd, timeout=args.rung_timeout, env=cache_env)
        tk = tokens(out)
        arts.append({"step": f"detect{i}", "rc": rc, "seconds": round(dt, 2),
                     "tokens": tk, "visible_text": out, "stderr": err[-300:]})
        tot += tk
    evidence = "\n\n".join(f"### {a['step']}\n{a['visible_text']}" for a in arts)
    return arts, tot, evidence


def grade(evidence, q):
    low = evidence.lower()
    cited = [g for g in q["ground_truth"]
             if g.lower() in low or Path(g).name.lower() in low]
    exists = [g for g in cited if (Path(SWIFT) / g).exists()]
    return {"ground_truth_cited": cited, "ground_truth_existing": exists,
            "pass": bool(exists)}


def main():
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    builds = {}
    for vname, code_root in VARIANTS:
        db = OUT / f"build_{vname}.db"
        if args.skip_prescan and db.exists():
            builds[vname] = str(db)
            print(f"prescan {vname}: reused {db}", flush=True)
            continue
        if db.exists():
            db.unlink()
        rc, out, err, dt = prescan(code_root, db)
        builds[vname] = str(db)
        (OUT / f"prescan_{vname}.log").write_text(
            f"rc={rc} seconds={dt:.1f}\n--- stdout ---\n{out}\n--- stderr ---\n{err}")
        print(f"prescan {vname}: rc={rc} {dt:.1f}s digest={db_digest(str(db))}",
              flush=True)
    (OUT / "prescan.json").write_text(json.dumps(
        {v: {"db": d, "digest": db_digest(d)} for v, d in builds.items()}, indent=1))

    rows = []
    for q in QS:
        for vname, code_root in VARIANTS:
            cache_env = stage_canonical(vname, builds[vname])
            t0 = time.monotonic()
            arts, tot, evidence = run_question(code_root, cache_env, q)
            dur = time.monotonic() - t0
            g = grade(evidence, q)
            qdir = OUT / "artifacts" / q["id"] / vname
            qdir.mkdir(parents=True, exist_ok=True)
            (qdir / "steps.json").write_text(json.dumps(
                [{k: a[k] for k in ("step", "rc", "seconds", "tokens")}
                 for a in arts], indent=1))
            (qdir / "evidence.txt").write_text(evidence)
            (qdir / "grade.json").write_text(json.dumps(g, indent=1))
            for a in arts:
                (qdir / f"step_{a['step']}.txt").write_text(a["visible_text"])
            rows.append({"question": q["id"], "variant": vname, "tokens": tot,
                         "pass": int(g["pass"]),
                         "gt_existing": ";".join(g["ground_truth_existing"])})
            print(f"{q['id']} {vname}: {tot} tok pass={g['pass']} {dur:.1f}s",
                  flush=True)
    # cleanup staged cache DBs (out of the repo tree already; drop copies)
    for vname, _ in VARIANTS:
        shutil.rmtree(OUT / f"cache_{vname}", ignore_errors=True)
    (OUT / "results.csv").write_text(
        "question,variant,tokens,pass,gt_existing\n" +
        "\n".join(f"{r['question']},{r['variant']},{r['tokens']},"
                  f"{r['pass']},{r['gt_existing']}" for r in rows) + "\n")
    print(f"stamp={stamp} done", flush=True)


if __name__ == "__main__":
    main()
