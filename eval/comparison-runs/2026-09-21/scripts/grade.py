#!/usr/bin/env python3
"""grade.py — aggregate run_variant outputs into the comparison table.

Usage: grade.py <corpus_json> <tip_out.json> <base_out.json>

Success rule (per question per variant): the ground-truth symbol name AND the
ground-truth file suffix appear anywhere in the concatenated step payloads
(detect + symbols + detail). A human spot-check of the evidence follows.
"""
import json
import sys

corpus_path, tip_path, base_path = sys.argv[1:4]
corpus = json.load(open(corpus_path))
tip = json.load(open(tip_path))
base = json.load(open(base_path))


def evidence_text(steps):
    parts = []
    for s in ("detect", "symbols", "detail"):
        parts.append(steps.get(s, {}).get("payload", ""))
    return "\n".join(parts)


def grade(question, steps):
    gt = question["ground_truth"]
    ev = evidence_text(steps)
    file_ok = gt["file"] in ev
    syms = gt["symbols"] if isinstance(gt.get("symbols"), list) else [gt["symbol"]]
    sym_ok = any(s in ev for s in syms)
    return file_ok and sym_ok, file_ok, sym_ok


rows = []
for q in corpus["questions"]:
    qid = q["id"]
    t_steps, b_steps = tip["questions"][qid], base["questions"][qid]

    def totals(steps):
        toks = sum(steps[s]["tokens"] for s in ("detect", "symbols", "detail"))
        calls = 2 + (0 if steps["detail"].get("skipped") else 1)
        return toks, calls

    t_toks, t_calls = totals(t_steps)
    b_toks, b_calls = totals(b_steps)
    t_ok, t_f, t_s = grade(q, t_steps)
    b_ok, b_f, b_s = grade(q, b_steps)
    rows.append({
        "id": qid, "question": q["question"], "query": q["query"],
        "tip_tokens": t_toks, "base_tokens": b_toks,
        "tip_calls": t_calls, "base_calls": b_calls,
        "tip_success": t_ok, "base_success": b_ok,
        "tip_detail": (t_f, t_s, t_steps["detail"].get("file"),
                       t_steps["detail"].get("name"), t_steps["detail"].get("line")),
        "base_detail": (b_f, b_s, b_steps["detail"].get("file"),
                        b_steps["detail"].get("name"), b_steps["detail"].get("line")),
    })

print(f"{'Q':<4} {'tip_tok':>8} {'base_tok':>8} {'tip_c':>5} {'base_c':>5} "
      f"{'tip_ok':>6} {'base_ok':>7}  question")
for r in rows:
    print(f"{r['id']:<4} {r['tip_tokens']:>8} {r['base_tokens']:>8} "
          f"{r['tip_calls']:>5} {r['base_calls']:>5} "
          f"{str(r['tip_success']):>6} {str(r['base_success']):>7}  {r['question'][:52]}")

tt = sum(r["tip_tokens"] for r in rows)
bt = sum(r["base_tokens"] for r in rows)
print(f"\nTOTAL tokens: tip={tt} base={bt} delta={tt-bt} ({100.0*(tt-bt)/bt:+.1f}%)")
print(f"TOTAL calls:  tip={sum(r['tip_calls'] for r in rows)} "
      f"base={sum(r['base_calls'] for r in rows)}")
print(f"Success:      tip={sum(r['tip_success'] for r in rows)}/{len(rows)} "
      f"base={sum(r['base_success'] for r in rows)}/{len(rows)}")
print(f"\nScan (session setup, sunk): tip={tip['scan']['tokens']} "
      f"base={base['scan']['tokens']}")
print("\nDetail targets chosen:")
for r in rows:
    print(f"  {r['id']} tip={r['tip_detail'][2:]} base={r['base_detail'][2:]}")
print("\nGround-truth file/symbol present in evidence (file_ok, sym_ok):")
for r in rows:
    print(f"  {r['id']} tip={r['tip_detail'][:2]} base={r['base_detail'][:2]}")

json.dump(rows, open("/tmp/vw_rows.json", "w"), indent=1)
