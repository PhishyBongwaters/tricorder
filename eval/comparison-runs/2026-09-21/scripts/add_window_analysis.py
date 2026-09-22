#!/usr/bin/env python3
"""Post-process swift-eval results: add per-question baseline-vs-branch
delta (raw tokens + percentage) and local-model context-window analysis.

Reads <outdir>/results.csv (+ steps.json artifacts), writes an enhanced
results_with_windows.md. Windows of interest for 16GB-VRAM local models:
32k, 64k, 128k. Flags any question where baseline overflows a window that
the branch still fits within.
"""
import csv
import json
import sys
from pathlib import Path

WINDOWS = [32768, 65536, 131072]

outdir = Path(sys.argv[1])
rows = list(csv.DictReader((outdir / "results.csv").read_text().splitlines()))
qs = sorted({r["question"] for r in rows})


def win_flag(base_tk, branch_tk):
    """Return list of windows where baseline overflows but branch fits."""
    flags = []
    for w in WINDOWS:
        if base_tk > w >= branch_tk:
            flags.append(f"{w // 1024}k")
    return flags


lines = ["# Swift-repo A/B: baseline vs branch head, with local-model window analysis",
         "",
         "Windows referenced: 32k / 64k / 128k (typical 16GB-VRAM local models).",
         "Delta = branch − baseline. Negative delta = branch saved tokens.",
         "",
         "## Per-question results",
         "",
         "| Question | Baseline tok | Branch tok | Δ raw | Δ % | Baseline calls | Branch calls | Baseline pass | Branch pass | Window flag |",
         "|---|---|---|---|---|---|---|---|---|---|"]

tot_b = tot_t = 0
for q in qs:
    rb = next(r for r in rows if r["question"] == q and r["variant"] == "baseline")
    rt = next(r for r in rows if r["question"] == q and r["variant"] == "branch")
    b, t = int(rb["tokens"]), int(rt["tokens"])
    tot_b += b
    tot_t += t
    d = t - b
    pct = (100.0 * d / b) if b else 0.0
    flags = win_flag(b, t)
    flag_txt = ("baseline overflows " + ", ".join(flags) + " but branch fits"
                if flags else "—")
    short = q.split(":")[0] if ":" in q else q
    lines.append(f"| {short} | {b:,} | {t:,} | {d:+,} | {pct:+.1f}% | "
                 f"{rb['calls']} | {rt['calls']} | "
                 f"{'PASS' if rb['pass'] == '1' else 'FAIL'} | "
                 f"{'PASS' if rt['pass'] == '1' else 'FAIL'} | {flag_txt} |")

d = tot_t - tot_b
pct = 100.0 * d / tot_b if tot_b else 0.0
lines += ["",
          "## Totals",
          "",
          f"- Tokens: baseline {tot_b:,}, branch {tot_t:,} → Δ {d:+,} ({pct:+.1f}%)",
          f"- Pass: baseline {sum(1 for r in rows if r['variant'] == 'baseline' and r['pass'] == '1')}/{len(qs)}, "
          f"branch {sum(1 for r in rows if r['variant'] == 'branch' and r['pass'] == '1')}/{len(qs)}",
          "",
          "## Where the totals sit vs local-model windows",
          ""]
for w in WINDOWS:
    kb = w // 1024
    b_fit = "fits" if tot_b <= w else "OVERFLOWS"
    t_fit = "fits" if tot_t <= w else "OVERFLOWS"
    lines.append(f"- {kb}k window: all-questions baseline total {tot_b:,} → {b_fit}; "
                 f"branch total {tot_t:,} → {t_fit}")
lines += ["",
          "## Per-question window placement (single-question navigation budget)",
          ""]
for q in qs:
    rb = next(r for r in rows if r["question"] == q and r["variant"] == "baseline")
    rt = next(r for r in rows if r["question"] == q and r["variant"] == "branch")
    b, t = int(rb["tokens"]), int(rt["tokens"])
    short = q.split(":")[0] if ":" in q else q
    place = []
    for w in WINDOWS:
        kb = w // 1024
        place.append(f"{kb}k: base {'fit' if b <= w else 'OVERFLOW'}/branch {'fit' if t <= w else 'OVERFLOW'}")
    lines.append(f"- {short}: " + "; ".join(place))

(outdir / "results_with_windows.md").write_text("\n".join(lines) + "\n")
print(str(outdir / "results_with_windows.md"))
