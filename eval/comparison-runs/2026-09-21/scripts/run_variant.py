#!/usr/bin/env python3
"""run_variant.py — scripted navigation loop for ONE tricorder variant.

Usage: run_variant.py <tricorder_root> <project_root> <corpus_json> <out_json>

Policy (identical for both variants; v3 "intended usage"):
  session setup (sunk, NOT charged per question): tricorder_scan(token_limit=1500)
  per question: detect(query) -> symbols(query) -> detail(best hit)

Each response payload is serialized exactly as an MCP agent would receive it
(json.dumps, default=str); tokens counted with tiktoken cl100k_base.
"""
import asyncio
import json
import sys

tricorder_root, project_root, corpus_path, out_path = sys.argv[1:5]
sys.path.insert(0, tricorder_root)
import tricorder_server as srv  # noqa: E402
import tiktoken  # noqa: E402

enc = tiktoken.get_encoding("cl100k_base")
corpus = json.load(open(corpus_path))


def payload_text(payload):
    return json.dumps(payload, default=str, ensure_ascii=False)


def best_hit(det_payload, sym_payload):
    for payload, key in ((sym_payload, "symbols"), (det_payload, "results")):
        items = (payload or {}).get(key) or []
        if items:
            h = items[0]
            f, n, ln = h.get("file"), h.get("name"), h.get("line", 0)
            if f and n:
                return f, n, int(ln or 0)
    return None


async def main():
    out = {"variant_root": project_root, "questions": {}}
    # Session setup: scan/index (sunk cost, reported separately, not per-question)
    scan_payload = await srv.tricorder_scan(project_root, token_limit=1500)
    scan_text = payload_text(scan_payload)
    out["scan"] = {"tokens": len(enc.encode(scan_text)), "chars": len(scan_text)}

    for q in corpus["questions"]:
        qid = q["id"]
        steps = {}
        det = await srv.tricorder_detect(project_root, q["query"])
        det_text = payload_text(det)
        steps["detect"] = {"tokens": len(enc.encode(det_text)),
                           "hits": len((det or {}).get("results") or [])}
        sym = await srv.tricorder_symbols(project_root, q["query"])
        sym_text = payload_text(sym)
        steps["symbols"] = {"tokens": len(enc.encode(sym_text)),
                            "hits": len((sym or {}).get("symbols") or [])}
        hit = best_hit(det, sym)
        if hit:
            f, n, ln = hit
            d = await srv.tricorder_detail(project_root, f, n, ln)
            d_text = payload_text(d)
            steps["detail"] = {"tokens": len(enc.encode(d_text)),
                               "file": f, "name": n, "line": ln}
        else:
            steps["detail"] = {"tokens": 0, "skipped": True,
                               "file": None, "name": None, "line": None}
        # keep full payloads for grading (evidence), but cap stored size
        steps["detect"]["payload"] = det_text[:200000]
        steps["symbols"]["payload"] = sym_text[:200000]
        steps["detail"]["payload"] = d_text[:200000] if hit else ""
        out["questions"][qid] = steps
        print(f"done {qid}", flush=True)
        json.dump(out, open(out_path, "w"))

    json.dump(out, open(out_path, "w"), indent=1)
    print(f"wrote {out_path}", flush=True)


asyncio.run(main())
