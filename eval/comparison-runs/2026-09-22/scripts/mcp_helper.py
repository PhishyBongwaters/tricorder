"""MCP rung helper: fresh process per rung, imports one variant tree."""
import asyncio
import json
import sys


def main():
    code_root, op = sys.argv[1], sys.argv[2]
    sys.path.insert(0, code_root)
    import tricorder_server as srv  # noqa: E402
    if op == "detect":
        project_root, query = sys.argv[3], sys.argv[4]
        out = asyncio.run(srv.tricorder_detect(
            project_root, query, pre_index=query))
        print(json.dumps(out))
    else:
        sys.exit(f"unknown op {op}")


if __name__ == "__main__":
    main()
