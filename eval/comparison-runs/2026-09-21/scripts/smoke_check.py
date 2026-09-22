#!/usr/bin/env python3
"""Smoke test: stage scan DB for tip root, try candidate queries.

Named smoke_check.py (not *_test.py) so pytest never tries to collect it
as a test module. Also parses sys.argv only under __main__ so an import
never raises IndexError under bare `pytest` collection.
"""
import asyncio
import sys


async def main(tricorder_root: str, project_root: str) -> None:
    sys.path.insert(0, tricorder_root)
    import tricorder_server as srv  # noqa: E402

    print("scanning...", flush=True)
    scan = await srv.tricorder_scan(project_root, token_limit=1500)
    print("scan keys:", list(scan.keys())[:8], flush=True)
    queries = ["totp verification", "admin token", "collection access",
               "cipher update notification"]
    for q in queries:
        det = await srv.tricorder_detect(project_root, q)
        results = (det or {}).get("results") or []
        sym = await srv.tricorder_symbols(project_root, q)
        symbols = (sym or {}).get("symbols") or []
        print(f"Q={q!r}: detect_hits={len(results)} "
              f"first={[ (r.get('file'), r.get('name')) for r in results[:2] ]}", flush=True)
        print(f"Q={q!r}: symbol_hits={len(symbols)} "
              f"first={[ (s.get('file'), s.get('name')) for s in symbols[:2] ]}", flush=True)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(f"usage: {sys.argv[0]} <tricorder_root> <project_root>")
    asyncio.run(main(sys.argv[1], sys.argv[2]))
