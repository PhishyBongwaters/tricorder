#!/usr/bin/env python3
"""Probe remaining candidate queries (head was truncated in prior run)."""
import asyncio
import sys

tricorder_root, project_root = sys.argv[1], sys.argv[2]
sys.path.insert(0, tricorder_root)
import tricorder_server as srv  # noqa: E402

QUERIES = ["validate_totp_code", "totp code", "validate_token"]


async def main():
    for q in QUERIES:
        det = await srv.tricorder_detect(project_root, q)
        results = (det or {}).get("results") or []
        sym = await srv.tricorder_symbols(project_root, q)
        symbols = (sym or {}).get("symbols") or []
        print(f"=== Q={q!r} detect({len(results)}):")
        for r in results[:6]:
            print(f"  {r.get('file')}:{r.get('line')} {r.get('name')}")
        print(f"=== Q={q!r} symbols({len(symbols)}):")
        for s in symbols[:6]:
            print(f"  {s.get('file')}:{s.get('line')} {s.get('name')}")
        sys.stdout.flush()


asyncio.run(main())
