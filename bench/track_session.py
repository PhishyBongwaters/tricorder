#!/usr/bin/env python3
"""Parse Hermes session metrics from state.db and agent.log.

Usage:
    python track_session.py [SESSION_ID]                         # default mode
    python track_session.py --save REPORT_PATH [SESSION_ID]      # save report to file
    python track_session.py --all                                 # list all CLI sessions
    python track_session.py --step SESSION_ID                     # per-step tool call log
"""
import sys
import re
import os
import sqlite3
from pathlib import Path

DB_PATH = Path(os.path.expanduser("~")) / "AppData" / "Local" / "hermes" / "state.db"
LOG_PATH = Path(os.path.expanduser("~")) / "AppData" / "Local" / "hermes" / "logs" / "agent.log"


def get_session_id():
    with LOG_PATH.open("r", encoding="utf-8", errors="ignore") as f:
        for line in reversed(f.readlines()):
            m = re.search(r'\[([0-9]{8}_[0-9]{6}_[a-f0-9]+)\]', line)
            if m:
                return m.group(1)
    print("Error: No session ID found in log.")
    sys.exit(1)


def list_sessions():
    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()
    cur.execute("""
        SELECT id, model, billing_provider, input_tokens, output_tokens,
               cache_read_tokens, api_call_count, tool_call_count,
               estimated_cost_usd, actual_cost_usd, title, started_at
        FROM sessions
        WHERE source = 'cli' AND archived = 0
        ORDER BY started_at DESC
        LIMIT 20
    """)
    rows = cur.fetchall()
    if not rows:
        print("No CLI sessions found.")
        conn.close()
        return
    print(f"{'SESSION ID':>24s} | {'MODEL':20s} | {'INPUT':>10s} | {'OUTPUT':>8s} | {'CACHE':>10s} | {'API':>4s} | {'TOOLS':>5s} | TITLE")
    print("-" * 140)
    for r in rows:
        sid, model, provider, inp, out, cache, api, tools, est, act, title, ts = r
        from datetime import datetime
        dt = datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")
        title_short = (title or sid[:12])[:40]
        print(f"{sid:>24s} | {model:20s} | {inp:>10,} | {out:>8,} | {cache:>10,} | {api:>4d} | {tools:>5d} | {dt} {title_short}")
    conn.close()


def step_log(sid):
    """Per-step tool call trace from agent.log."""
    print(f"=== Step-by-Step Log for Session {sid} ===\n")
    with LOG_PATH.open("r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            if f"[{sid}]" not in line:
                continue
            # API calls
            if "API call #" in line:
                m = re.search(r'API call #(\d+): model=(\S+) provider=(\S+) in=(\d+) out=(\d+) total=(\d+) latency=([\d\.]+)s', line)
                if m:
                    print(f"  [{int(m.group(1)):>2d}] API: in={int(m.group(4)):>8,} out={int(m.group(5)):>6,} total={int(m.group(6)):>9,} latency={m.group(7)}s")
            # Tool calls
            if "agent.tool_executor: tool" in line:
                m = re.search(r'tool (\w+) completed \(([\d\.]+)s, (\d+) chars\)', line)
                if m:
                    print(f"  tool {m.group(1):20s}: {m.group(2):>6}s  {m.group(3):>6} chars")
            # Turn ended
            if "Turn ended" in line:
                m = re.search(r'Turn ended:.*api_calls=(\d+)/(\d+).*tool_turns=(\d+)', line)
                if m:
                    print(f"  turn ended: api_calls={m.group(1)}/{m.group(2)} tool_turns={m.group(3)}")


def build_report(sid):
    """Build metrics report string for a session. Returns (report_text, tool_counts, tools_log)."""
    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()
    cur.execute("""
        SELECT model, billing_provider, input_tokens, output_tokens,
               cache_read_tokens, cache_write_tokens, reasoning_tokens,
               api_call_count, tool_call_count, estimated_cost_usd,
               actual_cost_usd, title, started_at, ended_at
        FROM sessions WHERE id = ?
    """, (sid,))
    row = cur.fetchone()
    conn.close()

    if not row:
        return f"Error: Session {sid} not found in DB.", {}, []

    model, provider, inp, out, cache_read, cache_write, reasoning, api, tools, est, act, title, started, ended = row

    api_calls = []
    tools_log = []
    with LOG_PATH.open("r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            if f"[{sid}]" not in line:
                continue
            m = re.search(r'API call #(\d+): model=(\S+) provider=(\S+) in=(\d+) out=(\d+) total=(\d+) latency=([\d\.]+)s', line)
            if m:
                api_calls.append({
                    "num": int(m.group(1)), "model": m.group(2),
                    "in": int(m.group(4)), "out": int(m.group(5)),
                    "total": int(m.group(6)), "latency": float(m.group(7))
                })
            m2 = re.search(r'tool (\w+) completed \(([\d\.]+)s, (\d+) chars\)', line)
            if m2:
                tools_log.append({"name": m2.group(1), "duration": float(m2.group(2)), "chars": int(m2.group(3)), "ts": None})

    # Per-call "in" is the RAW prompt/context sent that call (grows as the conversation
    # accumulates). Sum of all "in" = billed input_tokens + cache_read_tokens, because
    # cached context is re-sent each call but billed through the cache_read bucket.
    api_calls.sort(key=lambda c: c["num"])

    tool_counts = {}
    for t in tools_log:
        tool_counts[t["name"]] = tool_counts.get(t["name"], 0) + 1

    duration = 0
    if started and ended:
        duration = ended - started

    lines = []
    lines.append(f"# Metrics Report: Session {sid}")
    if title:
        lines.append(f"**Title:** {title}")
    lines.append(f"**Model:** {model} ({provider})")
    lines.append(f"**Duration:** {duration:.0f}s")
    lines.append("")
    lines.append("## Aggregate Metrics")
    lines.append(f"- Tool calls: {tools}")
    lines.append(f"- API calls: {api}")
    lines.append(f"- Input tokens: {inp:,}")
    lines.append(f"- Output tokens: {out:,}")
    lines.append(f"- Cache read: {cache_read:,}")
    lines.append(f"- Cache write: {cache_write:,}")
    lines.append(f"- Reasoning tokens: {reasoning:,}")
    lines.append(f"- Actual cost: {act if act else 'N/A'}")
    if api_calls:
        sum_raw_in = sum(c["in"] for c in api_calls)
        sum_out = sum(c["out"] for c in api_calls)
        lines.append(f"- Reconciliation: raw input sent = {sum_raw_in:,} = billed input {inp:,} + cache read {cache_read:,}")
        lines.append(f"- Sum of per-call output: {sum_out:,} (DB reports {out:,})")
    lines.append("")
    lines.append("## Per-API-Call Breakdown")
    lines.append("_'in' = raw prompt/context sent that call (grows as conversation accumulates). ")
    lines.append("Sum of 'in' across calls = billed input + cache read._")
    for c in api_calls:
        lines.append(f"- Call #{c['num']}: in={c['in']:,} out={c['out']:,} total={c['total']:,} latency={c['latency']}s")
    lines.append("")
    lines.append("## Tool Usage Breakdown")
    for name, count in sorted(tool_counts.items(), key=lambda x: -x[1]):
        lines.append(f"- {name}: {count}")
    lines.append("")
    lines.append("## Step-by-Step Trace")
    with LOG_PATH.open("r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            if f"[{sid}]" not in line:
                continue
            if "API call #" in line:
                m = re.search(r'API call #(\d+): model=(\S+) provider=(\S+) in=(\d+) out=(\d+) total=(\d+) latency=([\d\.]+)s', line)
                if m:
                    lines.append(f"- [{int(m.group(1))}] API: in={int(m.group(4)):,} out={int(m.group(5)):,} total={int(m.group(6)):,} latency={m.group(7)}s")
            if "agent.tool_executor: tool" in line:
                m = re.search(r'tool (\w+) completed \(([\d\.]+)s, (\d+) chars\)', line)
                if m:
                    lines.append(f"- tool {m.group(1)}: {m.group(2)}s {m.group(3)} chars")
            if "Turn ended" in line:
                m = re.search(r'Turn ended:.*api_calls=(\d+)/(\d+).*tool_turns=(\d+)', line)
                if m:
                    lines.append(f"- turn ended: api_calls={m.group(1)}/{m.group(2)} tool_turns={m.group(3)}")
    return "\n".join(lines), tool_counts, tools_log


if __name__ == "__main__":
    if "--all" in sys.argv:
        list_sessions()
    elif "--save" in sys.argv:
        save_idx = sys.argv.index("--save")
        report_path = sys.argv[save_idx + 1]
        sid = sys.argv[save_idx + 2] if len(sys.argv) > save_idx + 2 else get_session_id()
        report, _, _ = build_report(sid)
        Path(report_path).write_text(report, encoding="utf-8")
        print(f"Report saved to {report_path} ({len(report)} chars)")
    elif "--step" in sys.argv:
        sid = sys.argv[2] if len(sys.argv) > 2 else get_session_id()
        step_log(sid)
    else:
        sid = get_session_id()
        report, _, _ = build_report(sid)
        print(report)
