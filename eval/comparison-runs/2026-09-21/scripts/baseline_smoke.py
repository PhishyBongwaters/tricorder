#!/usr/bin/env python3
"""Baseline smoke test: verify baseline server scans + detects on vw-base root."""
import asyncio
import sys

sys.path.insert(0, sys.argv[1])
import tricorder_server as srv  # noqa: E402

ROOT = "/home/hatch/workspace/comparisons/vw-base/vaultwarden"


async def main():
    scan = await srv.tricorder_scan(ROOT, token_limit=1500)
    print("scan keys:", sorted(scan.keys()), flush=True)
    det = await srv.tricorder_detect(ROOT, "totp code")
    res = (det or {}).get("results") or []
    print(f"detect hits: {len(res)}", flush=True)
    for r in res[:4]:
        print("  ", r.get("file"), r.get("line"), r.get("name"), flush=True)
    sym = await srv.tricorder_symbols(ROOT, "totp code")
    s = (sym or {}).get("symbols") or []
    print(f"symbol hits: {len(s)}", flush=True)
    for x in s[:4]:
        print("  ", x.get("file"), x.get("line"), x.get("name"), flush=True)


asyncio.run(main())
