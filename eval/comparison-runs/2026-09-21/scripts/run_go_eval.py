#!/usr/bin/env python3
"""
run_go_eval.py — base-vs-tip A/B on golang/go, method v3 (MCP rung surface).

Compares two tricorder code trees (baseline worktree @438fd0b vs branch
tip) on identical scripted navigation loops:

  per task: detect(q1) -> symbols(q1) -> detail(best q1 hit) ->
            detect(q2) -> symbols(q2) -> detail(best q2 hit)   (6 calls/task)

Methodology mirrors run_eval_v3.py --rung-via mcp (the v3 harness), except
the pre-scanned DB is staged via TRICORDER_CACHE_HOME per arm instead of
the in-repo canonical location, so the go clone stays pristine (read-only).

Metrics: agent-visible tokens per rung counted with utils.count_tokens
(tiktoken cl100k) from the code tree under test; true per-command call
counts; pre-scan sunk one-time cost (recorded, never charged per task);
symmetric entity grader; 3x replication.

Usage: python run_go_eval.py [--runs 3] [--task G1-gc-mark-phase]
       [--arm base|tip]   (default: both arms, sequentially)
"""
import argparse
import csv
import json
import os
import shutil
import statistics
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
HOME = Path.home()
COMPARISONS = HERE  # ~/workspace/comparisons
GO_REPO = str(COMPARISONS / "go")

ARMS = {
    # 438fd0b = merge-base of fix/parallel-qualify onto origin/dev/db-map
    # (parent of the branch's first fix commit 3295cb5). Own worktree so
    # sibling workers' checkouts can't be removed under us mid-run.
    "base": str(COMPARISONS / "tricorder-baseline-go"),
    "tip": str(Path("~/workspace/tricorder").expanduser()),  # fix/parallel-qualify
}

VENV_PY = str(HOME / "workspace" / "tricorder-venv" / "bin" / "python")
TIKTOKEN_CACHE = str(HOME / "workspace" / ".cache" / "tiktoken")
MCP_HELPER = [VENV_PY, str(HOME / "workspace" / "tricorder-linux-eval"
                           / "mcp_rung_helper.py")]
CMD_TIMEOUT = 600

ap = argparse.ArgumentParser()
ap.add_argument("--runs", type=int, default=3)
ap.add_argument("--task", default=None)
ap.add_argument("--corpus", default=str(COMPARISONS / "tasks_go.json"))
ap.add_argument("--arm", default="both", choices=["base", "tip", "both"])
args = ap.parse_args()

CHILD_ENV = dict(os.environ)
CHILD_ENV["TIKTOKEN_CACHE_DIR"] = TIKTOKEN_CACHE  # same pin as venv activate


def arm_env(arm):
    env = dict(CHILD_ENV)
    env["TRICORDER_CACHE_HOME"] = str(COMPARISONS / f"cache-go-{arm}")
    return env


def sh(cmd, timeout=CMD_TIMEOUT, env=None):
    t0 = time.monotonic()
    try:
        p = subprocess.run(cmd, capture_output=True, text=True,
                           timeout=timeout, env=env or CHILD_ENV)
        return p.returncode, p.stdout, p.stderr, time.monotonic() - t0
    except subprocess.TimeoutExpired as e:
        return -1, (e.stdout or "") if isinstance(e.stdout, str) else "", \
            "TIMEOUT", time.monotonic() - t0


def load_count_tokens(code_root):
    sys.path.insert(0, code_root)
    import importlib
    import utils
    importlib.reload(utils)
    return utils.count_tokens


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


def run_arm(arm, tasks, outdir, count_tokens):
    code_root = ARMS[arm]
    env = arm_env(arm)
    cache_db_dir = Path(env["TRICORDER_CACHE_HOME"]) / "db"
    cache_db_dir.mkdir(parents=True, exist_ok=True)

    # --- PRE-SCAN, once per arm (sunk one-time cost, never charged/task).
    # DEVIATION from run_eval_v3.py: v3 runs the full map command
    # (--map-tokens 500). On golang/go (16k files, 1.4GB DB) the map TEXT
    # RENDER after the scan spins single-threaded for 15+ min (observed),
    # while the DB scan itself completes in ~7 min. The rungs only need the
    # DB, and v3 never puts the map into per-task context, so the pre-scan
    # builds the DB with --map-tokens 0 (get_repo_map early-outs: no render;
    # get_ranked_tags still performs the full dirty-file scan into the DB).
    # Sunk cost is reported as DB-build wall time; stdout tokens ~0.
    # If a staged DB already exists for this arm (previous run), reuse it:
    # the scan is deterministic for an unchanged repo.
    staged = cache_db_dir / "go.db"
    build_db = outdir / f"build_go_{arm}.db"
    if staged.exists() and staged.stat().st_size > 0:
        build = {"seconds": 0, "stdout_tokens": 0, "rc": 0,
                 "db": str(staged), "reused": True}
        print(f"[{arm}] reusing staged DB {staged}", flush=True)
    else:
        cmd = [VENV_PY, os.path.join(code_root, "tricorder.py"),
               "--root", GO_REPO, "--map-tokens", "0",
               "--format", "text", "--db-path", str(build_db)]
        rc, stdout, stderr, dt = sh(cmd, timeout=1800, env=env)
        build = {"seconds": round(dt, 2), "stdout_tokens": count_tokens(stdout),
                 "rc": rc, "db": str(build_db)}
        if rc != 0 or not build_db.exists():
            build["stderr_tail"] = stderr[-2000:]
        # Stage the build DB where the MCP server resolves it
        # (<cache>/db/go.db via TRICORDER_CACHE_HOME); the go clone is untouched.
        if build_db.exists():
            shutil.copyfile(build_db, staged)

    # Warm the persistent TAGS_CACHE (diskcache) with an UNMEASURED rung.
    # search_identifiers calls get_tags() for every file; the parallel
    # fresh-scan worker bypasses get_tags, so without this the first
    # measured rung would pay a ~4-5 min cold-parse on golang/go (16k
    # files) and pollute task 1's numbers. Warming is sunk index-build
    # cost, like the DB build above — never charged to a task.
    warm_t0 = time.monotonic()
    sh(MCP_HELPER + [code_root, "detect", GO_REPO, "warmup"],
       timeout=900, env=env)
    build["warm_seconds"] = round(time.monotonic() - warm_t0, 2)

    # Warm the cross-file index used by get_symbol_detail (detail rungs).
    # The first detail call builds the index from scratch (~10-15 min on
    # golang/go); it is disk-cached thereafter. Warm it here as sunk cost
    # so measured detail rungs hit the cache. Uses a known-good symbol.
    idx_t0 = time.monotonic()
    sh(MCP_HELPER + [code_root, "detail", GO_REPO,
                     "src/runtime/mgc.go", "gcBgMarkWorker", "1766"],
       timeout=1200, env=env)
    build["index_warm_seconds"] = round(time.monotonic() - idx_t0, 2)

    rows = []
    for task in tasks:
        for run in range(1, args.runs + 1):
            adir = outdir / "artifacts" / task["id"] / f"arm_{arm}" / \
                f"run{run}"
            # Resume: skip if this task/arm/run already completed.
            if (adir / "steps.json").exists():
                print(f"[{arm}] {task['id']} run{run}: already done, skipping",
                      flush=True)
                sj = json.loads((adir / "steps.json").read_text())
                g = json.loads((adir / "grade.json").read_text())
                m = json.loads((adir / "meta.json").read_text()) \
                    if (adir / "meta.json").exists() else {}
                tot_tk = sum(s["tokens"] for s in sj)
                rows.append({"task_id": task["id"], "arm": arm, "run": run,
                             "tokens": tot_tk, "calls": len(sj),
                             "duration_s": m.get("duration_s", 0),
                             "entities_matched": g["n_matched"],
                             "entities_total": g["n_total"],
                             "pass": int(g["pass"])})
                continue
            adir.mkdir(parents=True)
            artifacts, tot_tk, calls = [], 0, 0
            evidence_parts, seen = [], {}
            kw = task["keywords"]
            t0 = time.monotonic()
            for qi, q in enumerate(kw, start=1):
                for rung in ("detect", "symbols"):
                    name = f"{rung}{qi}"
                    cmd = MCP_HELPER + [code_root, rung, GO_REPO, q]
                    rc, out, err, dt = sh(cmd, env=env)
                    tk = count_tokens(out)
                    artifacts.append({"step": name, "rc": rc,
                                      "seconds": round(dt, 2), "tokens": tk,
                                      "visible_text": out})
                    seen[name] = out
                    evidence_parts.append(f"### {name}\n{out}")
                    tot_tk += tk
                    calls += 1
                # detail rung on best hit (symbols first, detect fallback)
                hit = parse_mcp_hit(seen.get(f"symbols{qi}", ""), "symbols")
                if hit is None:
                    hit = parse_mcp_hit(seen.get(f"detect{qi}", ""), "results")
                name = f"detail{qi}"
                if hit and hit[0] and hit[1]:
                    f, nm, ln = hit
                    cmd = MCP_HELPER + [code_root, "detail", GO_REPO,
                                        f, nm, ln or "0"]
                else:
                    cmd = ["echo", "NO_HIT_FOR_DETAIL"]
                rc, out, err, dt = sh(cmd, env=env)
                tk = count_tokens(out)
                artifacts.append({"step": name, "rc": rc,
                                  "seconds": round(dt, 2), "tokens": tk,
                                  "visible_text": out})
                seen[name] = out
                evidence_parts.append(f"### {name}\n{out}")
                tot_tk += tk
                calls += 1
            dur = time.monotonic() - t0
            evidence = "\n\n".join(evidence_parts)
            low = evidence.lower()
            ents = task["rubric_entities"]
            matched = [e for e in ents if e.lower() in low]
            gt = any(Path(f).name.lower() in low or f.lower() in low
                     for f in task["ground_truth_files"])
            ok = (len(matched) / len(ents) >= task["pass_threshold"]) and gt
            g = {"matched": matched, "n_matched": len(matched),
                 "n_total": len(ents), "ground_truth_cited": gt,
                 "pass": ok}
            (adir / "steps.json").write_text(json.dumps(
                [{k: s[k] for k in ("step", "rc", "seconds", "tokens")}
                 for s in artifacts], indent=1))
            (adir / "evidence.txt").write_text(evidence)
            (adir / "grade.json").write_text(json.dumps(g, indent=1))
            (adir / "meta.json").write_text(json.dumps(
                {"duration_s": round(dur, 2), "tokens": tot_tk,
                 "calls": calls}, indent=1))
            for s in artifacts:
                (adir / f"step_{s['step']}.txt").write_text(s["visible_text"])
            rows.append({"task_id": task["id"], "arm": arm, "run": run,
                         "tokens": tot_tk, "calls": calls,
                         "duration_s": round(dur, 2),
                         "entities_matched": g["n_matched"],
                         "entities_total": g["n_total"],
                         "pass": int(g["pass"])})
    return rows, build


def main():
    corpus = json.loads(Path(args.corpus).read_text())
    tasks = [t for t in corpus["tasks"] if t["status"] == "available"]
    if args.task:
        tasks = [t for t in tasks if t["id"] == args.task]
    arms = ["base", "tip"] if args.arm == "both" else [args.arm]

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    outdir = COMPARISONS / "results-go" / f"{stamp}-go-basetip"
    outdir.mkdir(parents=True)

    all_rows, builds = [], {}
    for arm in arms:
        count_tokens = load_count_tokens(ARMS[arm])

        def tokens(text):
            return count_tokens(text, "gpt-4")

        rows, build = run_arm(arm, tasks, outdir, tokens)
        all_rows.extend(rows)
        builds[arm] = build
        print(f"[{arm}] pre-scan: rc={build['rc']} "
              f"{build['stdout_tokens']:,} tokens, {build['seconds']:.0f}s; "
              f"{len(rows)} task-runs done", flush=True)

    with open(outdir / "results.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(all_rows[0].keys()))
        w.writeheader()
        w.writerows(all_rows)

    agg = {}
    for arm in arms:
        vr = [r for r in all_rows if r["arm"] == arm]
        tids = sorted({r["task_id"] for r in vr})
        per_task_mean = statistics.mean(
            statistics.mean(r["tokens"] for r in vr if r["task_id"] == t)
            for t in tids)
        step_means = {}
        for r in vr:
            sj = json.loads((outdir / "artifacts" / r["task_id"] /
                             f"arm_{arm}" / f"run{r['run']}" /
                             "steps.json").read_text())
            for s in sj:
                step_means.setdefault(s["step"], []).append(s["tokens"])
        agg[arm] = {
            "mean_tokens": per_task_mean,
            "mean_calls": statistics.mean(r["calls"] for r in vr),
            "mean_duration_s": statistics.mean(r["duration_s"] for r in vr),
            "pass_rate": sum(r["pass"] for r in vr) / len(vr),
            "deterministic": len({(r["tokens"], r["pass"]) for r in vr})
                             == len(tids),
            "step_means": {k: round(statistics.mean(v))
                           for k, v in step_means.items()},
        }

    B, T = agg["base"], agg["tip"]

    def delta(a, b):
        d = a - b
        s = f"{d:+,.0f}"
        if b:
            s += f" ({d / b:+.1%})"
        return s

    md = f"""# golang/go base-vs-tip — {stamp} (method v3, MCP rung surface)

Baseline: {ARMS['base']} @ {subprocess.run(['git','-C',ARMS['base'],'rev-parse','--short','HEAD'],capture_output=True,text=True).stdout.strip()} (merge-base of fix/parallel-qualify onto origin/dev/db-map)
Tip: {ARMS['tip']} @ {subprocess.run(['git','-C',ARMS['tip'],'rev-parse','--short','HEAD'],capture_output=True,text=True).stdout.strip()} (fix/parallel-qualify head)
Repo: golang/go @ 8002a0da (shallow, 15,927 files), read-only; DBs per arm via TRICORDER_CACHE_HOME.
Scripted policy per task: detect -> symbols -> detail per keyword (2 keywords, 6 calls/task).
Tokenizer: tiktoken cl100k via utils.count_tokens from the tree under test. Reps: {args.runs}x.

| Metric (mean/task) | base | tip | Δ (tip−base) |
|---|---|---|---|
| Agent-visible tokens, marginal | {B['mean_tokens']:,.0f} | {T['mean_tokens']:,.0f} | {delta(T['mean_tokens'], B['mean_tokens'])} |
| Tool calls (true count) | {B['mean_calls']:.1f} | {T['mean_calls']:.1f} | {T['mean_calls'] - B['mean_calls']:+.1f} |
| Duration, wall s | {B['mean_duration_s']:.1f} | {T['mean_duration_s']:.1f} | {T['mean_duration_s'] - B['mean_duration_s']:+.1f}s |
| Pass rate (symmetric entity grader) | {B['pass_rate']:.0%} | {T['pass_rate']:.0%} | — |

One-time pre-scan (NOT charged per task): base {builds['base']['stdout_tokens']:,} map tokens / {builds['base']['seconds']:.0f}s DB build (rc={builds['base']['rc']}) + {builds['base'].get('warm_seconds', 0):.0f}s tags-cache warm + {builds['base'].get('index_warm_seconds', 0):.0f}s index warm; tip {builds['tip']['stdout_tokens']:,} map tokens / {builds['tip']['seconds']:.0f}s DB build (rc={builds['tip']['rc']}) + {builds['tip'].get('warm_seconds', 0):.0f}s warm + {builds['tip'].get('index_warm_seconds', 0):.0f}s index warm. (Map-text render skipped via --map-tokens 0: on golang/go the render spins 15+ min single-threaded; the DB scan is identical and v3 never puts the map in per-task context.)

## Per-rung token means (base | tip)

| Rung | base | tip |
|------|------|-----|
"""
    for step in ["detect1", "symbols1", "detail1", "detect2", "symbols2", "detail2"]:
        md += f"| {step} | {agg['base']['step_means'].get(step, 0):,} | {agg['tip']['step_means'].get(step, 0):,} |\n"

    md += "\n## Per-task detail (mean tokens over reps)\n\n"
    md += "| Task | base tok | tip tok | base calls | tip calls | base pass | tip pass |\n"
    md += "|------|----------|---------|------------|-----------|-----------|----------|\n"
    for t in tasks:
        br = [r for r in all_rows if r["task_id"] == t["id"] and r["arm"] == "base"]
        tr = [r for r in all_rows if r["task_id"] == t["id"] and r["arm"] == "tip"]
        md += (f"| {t['id']} | {statistics.mean(r['tokens'] for r in br):,.0f} | "
               f"{statistics.mean(r['tokens'] for r in tr):,.0f} | "
               f"{br[0]['calls']} | {tr[0]['calls']} | "
               f"{'PASS' if all(r['pass'] for r in br) else 'MIXED/FAIL'} | "
               f"{'PASS' if all(r['pass'] for r in tr) else 'MIXED/FAIL'} |\n")

    md += f"""
## Replication

- base deterministic (identical tokens+pass across reps): {agg['base']['deterministic']}
- tip deterministic: {agg['tip']['deterministic']}

## Caveats

- Scripted escalation policies, not a live agent: measures tool-path efficiency, not agentic search.
- Each rung runs in a fresh process; Tricorder construction cost is paid per rung (see durations).
- Every number traces to artifacts/ in this directory (steps.json, step_<name>.txt, evidence.txt, grade.json per task/arm/run; results.csv).
"""
    (outdir / "results.md").write_text(md)
    print(md)
    print(f"\nArtifacts: {outdir}")


if __name__ == "__main__":
    main()
