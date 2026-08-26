#!/usr/bin/env python3
"""Phase 2: Large repository torture tests."""
import asyncio
import time
import sys
import tempfile
import os
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from utils import repo_budget, discover_src_files, count_tokens, read_text
from tricorder_server import (
    tricorder_scan, tricorder_symbols, tricorder_detect,
    _tier_history_store,
)


REPOS = [
    ("linux", r"D:\Projects\Tricorder-Testing-Repos\linux"),
    ("LibreChat", r"D:\Projects\Tricorder-Testing-Repos\LibreChat"),
    ("vaultwarden", r"D:\Projects\Tricorder-Testing-Repos\vaultwarden"),
    ("rails", r"D:\Projects\Tricorder-Testing-Repos\rails"),
    ("spring-boot", r"D:\Projects\Tricorder-Testing-Repos\spring-boot"),
]


def measure_discovery(repo_root: str, name: str) -> dict:
    """Measure file discovery metrics."""
    start = time.perf_counter()
    files = discover_src_files(repo_root, use_gitignore=True)
    elapsed = time.perf_counter() - start

    exts = {}
    total_lines = 0
    for f in files:
        try:
            txt = read_text(f, silent=True) or ""
            lines = txt.count("\n")
            total_lines += lines
            ext = Path(f).suffix.lower()
            exts[ext] = exts.get(ext, 0) + 1
        except Exception:
            pass

    return {
        "name": name,
        "file_count": len(files),
        "extensions": dict(sorted(exts.items(), key=lambda x: -x[1])[:10]),
        "total_lines_estimate": total_lines,
        "discover_time_s": round(elapsed, 3),
    }


def measure_budget(repo_root: str, name: str) -> dict:
    """Measure repo budget (full_repo_estimate, token counts)."""
    start = time.perf_counter()
    budget = repo_budget(repo_root, map_tokens=2048)
    elapsed = time.perf_counter() - start

    return {
        "name": name,
        "full_repo_estimate": budget["full_repo_estimate"],
        "savings_pct": budget["savings_pct"],
        "budget_time_s": round(elapsed, 3),
    }


async def measure_probe(repo_root: str, name: str, probe_query: str = "main") -> dict:
    """Measure probe digit size reduction."""
    start = time.perf_counter()

    # Full scan at tier 0
    scan_result = await tricorder_scan(
        project_root=repo_root,
        chat_files=[],
        token_limit=100000,
        tier=0,
        context_lines=1,
        output_format="text",
        output_file=None,
        exclude_globs=None,
        dry_run=False,
        max_files=1000,
        probe_files=None,
    )

    elapsed = time.perf_counter() - start

    if "error" in scan_result:
        return {"name": name, "error": scan_result["error"]}

    scan_tokens = scan_result.get("estimated_tokens", 0)
    scan_files = scan_result.get("files_processed", 0)

    # Probe digit
    probe_start = time.perf_counter()
    probed = await tricorder_detect(
        project_root=repo_root,
        query=probe_query,
        search_mode="substring",
        max_results=10,
    )

    probe_elapsed = time.perf_counter() - probe_start
    probe_count = len(probed.get("results", []))

    return {
        "name": name,
        "scan_files": scan_files,
        "scan_tokens": scan_tokens,
        "probe_count": probe_count,
        "probe_time_s": round(probe_elapsed, 3),
        "total_time_s": round(elapsed + probe_elapsed, 3),
    }


async def measure_symbols(repo_root: str, name: str) -> dict:
    """Measure symbol extraction metrics."""
    start = time.perf_counter()

    # Sample first 20 files for symbol density
    files = discover_src_files(repo_root, use_gitignore=True)[:20]
    total_symbols = 0
    languages = set()

    for f in files:
        try:
            result = await tricorder_symbols(
                project_root=repo_root,
                file=str(f),
                symbol_types=None,
                trust_mode="scm",
                chat_files=[],
            )
            symbols = result.get("symbols", [])
            total_symbols += len(symbols)
            for s in symbols:
                languages.add(s.get("language", "unknown"))
        except Exception:
            pass

    elapsed = time.perf_counter() - start
    return {
        "name": name,
        "sample_files": len(files),
        "sample_symbols": total_symbols,
        "avg_symbols_per_file": round(total_symbols / max(len(files), 1), 1),
        "languages_found": len(languages),
        "symbol_time_s": round(elapsed, 3),
    }


async def main():
    print("=" * 70)
    print("PHASE 2: LARGE REPOSITORY TORTURE TESTS")
    print("=" * 70)

    # Clear tier history for clean memory test
    _tier_history_store.clear()

    results = {}

    for name, repo in REPOS:
        if not Path(repo).exists():
            print(f"\n[SKIP] {name}: {repo} not found")
            continue

        print(f"\n{'=' * 40}")
        print(f"REPO: {name}")
        print(f"ROOT: {repo}")
        print(f"{'=' * 40}")

        # 1. Discovery
        disc = measure_discovery(repo, name)
        print(f"  Discovery:   {disc['file_count']:>6} files  |  "
              f"{disc['total_lines_estimate']:>10} est. lines  |  "
              f"{disc['discover_time_s']:>6.3f}s")
        results.setdefault(name, {})["discovery"] = disc

        # 2. Budget
        bud = measure_budget(repo, name)
        print(f"  Budget:      {bud['full_repo_estimate']:>10} tokens  |  "
              f"{bud['savings_pct']:>5.1f}% savings  |  "
              f"{bud['budget_time_s']:>6.3f}s")
        results.setdefault(name, {})["budget"] = bud

        # 3. Probe
        probe_name = name
        if name == "linux":
            probe_query = "retransmission"
        elif name == "rails":
            probe_query = "ActiveRecord"
        elif name == "spring-boot":
            probe_query = "SpringApplication"
        else:
            probe_query = "main"

        prob = await measure_probe(repo, probe_name, probe_query)
        if "error" in prob:
            print(f"  Probe:       ERROR: {prob['error']}")
        else:
            print(f"  Probe:       {prob['scan_files']:>6} scan files  |  "
                  f"{prob['probe_count']:>4} results  |  "
                  f"{prob['probe_time_s']:>6.3f}s probe")
        results.setdefault(name, {})["probe"] = prob

        # 4. Symbols
        sym = await measure_symbols(repo, name)
        print(f"  Symbols:     {sym['sample_files']:>3} files  |  "
              f"{sym['sample_symbols']:>5} symbols  |  "
              f"{sym['avg_symbols_per_file']:>5.1f} avg  |  "
              f"{sym['symbol_time_s']:>6.3f}s")
        results.setdefault(name, {})["symbols"] = sym

    # 5. Memory footprint
    print(f"\n{'=' * 40}")
    print("MEMORY FOOTPRINT")
    print(f"{'=' * 40}")
    print(f"  Tier history entries: {len(_tier_history_store)}")
    print(f"  Max tier history:    128 (bounded LRU)")
    results["memory"] = {
        "tier_history_entries": len(_tier_history_store),
        "max_tier_history": 128,
    }

    # Save results
    out_path = Path(__file__).parent.parent / "bench_temp" / "torture_results.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2)

    print(f"\nResults saved to: {out_path}")
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)

    for name in results:
        if name == "memory":
            continue
        r = results[name]
        if "error" in r.get("probe", {}):
            print(f"  {name:20s}  ERROR: {r['probe']['error']}")
        else:
            files = r.get("discovery", {}).get("file_count", 0)
            tokens = r.get("budget", {}).get("full_repo_estimate", 0)
            probe_count = r.get("probe", {}).get("probe_count", 0)
            print(f"  {name:20s}  {files:>6} files  |  {tokens:>10} tokens  |  {probe_count:>4} probe hits")


if __name__ == "__main__":
    asyncio.run(main())