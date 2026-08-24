#!/usr/bin/env python3
"""
ctags probe — fast symbol index for repo filtering before tree-sitter.
"""

import subprocess
import os
import sys
import time
from pathlib import Path
from typing import List, Tuple, Optional
import fnmatch

CTAGS_MAX_SOURCE_FILES = 20000

def _count_source_files(project_root: str) -> int:
    root = Path(project_root)
    n = 0
    for _ in root.rglob("*"):
        n += 1
        if n > CTAGS_MAX_SOURCE_FILES:
            return n + 1
    return n

def _run_ctags(project_root: str, tags_file: Path) -> bool:
    if _count_source_files(project_root) > CTAGS_MAX_SOURCE_FILES:
        print(f"[ctags_probe] SKIP index: >{CTAGS_MAX_SOURCE_FILES} files in {project_root} (rg fallback only)", file=sys.stderr)
        return False
    exclude = [
        "--exclude=*.min.js", "--exclude=*.min.css", "--exclude=vendor/**",
        "--exclude=third_party/**", "--exclude=.git/**", "--exclude=build/**",
        "--exclude=dist/**", "--exclude=node_modules/**", "--exclude=__pycache__/**", "--exclude=*.pyc",
    ]
    cmd = [
        "ctags", "-R",
        "--languages=C,C++,Python,JavaScript,TypeScript,Go,Rust,Java,Kotlin,Swift,PHP,Ruby,Perl,Lua,Shell,SQL,HTML,CSS,JSON,YAML,TOML,XML,Markdown",
        "--fields=+n", "-f", str(tags_file), *exclude, project_root,
    ]
    try:
        subprocess.run(cmd, capture_output=True, timeout=120, check=True)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        return False

def ensure_ctags_index(project_root: str, max_age_days: int = 7) -> Optional[Path]:
    tags_file = Path(project_root) / "tags"
    if tags_file.exists():
        # Refuse oversized/stale indexes: a sane per-repo tags index is a few MB.
        # A multi-hundred-MB one is a corrupt walk of a huge tree — never trust it.
        if tags_file.stat().st_size > 100 * 1024 * 1024:
            print(f"[ctags_probe] SKIP huge existing index {tags_file} "
                  f"({tags_file.stat().st_size // (1024*1024)}MB); rg-only",
                  file=sys.stderr)
            return None
        age_days = (time.time() - tags_file.stat().st_mtime) / 86400
        if age_days <= max_age_days:
            return tags_file
    if _run_ctags(project_root, tags_file):
        return tags_file
    return None

def probe_symbol(tags_file: Path, symbol: str) -> List[Tuple[str, int]]:
    if not tags_file.exists():
        return []
    lookup = symbol.rsplit("::", 1)[-1].rsplit(".", 1)[-1]
    results = []
    try:
        with open(tags_file, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('!'):
                    continue
                if line.startswith(lookup + "\t") or f"\t{lookup}\t" in line:
                    parts = line.split("\t")
                    if len(parts) >= 2:
                        file_path = parts[1]
                        lineno = 0
                        for p in parts:
                            if p.startswith("line:"):
                                try:
                                    lineno = int(p[5:])
                                except ValueError:
                                    pass
                        results.append((file_path, lineno))
    except Exception:
        pass
    return results

def rg_fallback(project_root: str, symbol: str, lang: str = "") -> List[Tuple[str, int]]:
    cmd = ["rg", "-n", "--no-heading", "-w", "-g", "*.c", "-g", "*.h", "-g", "*.cpp", "-g", "*.hpp", "-g", "*.cc", "-g", "*.py", "-g", "*.js", "-g", "*.ts", "-g", "*.go", "-g", "*.rs", "-g", "*.java", "-g", "*.rb", "-g", "*.php", "-g", "*.sh", "-g", "*.erl", "-g", "*.ex", "-g", "*.kt", "-g", "*.swift"]
    if lang:
        cmd += ["-t", lang]
    cmd += [symbol, project_root]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=30, check=False)
        if r.returncode == 0:
            results = []
            for line in r.stdout.strip().splitlines():
                parts = line.rsplit(":", 2)
                if len(parts) >= 2:
                    try:
                        results.append((parts[0], int(parts[1])))
                    except ValueError:
                        results.append((parts[0], 0))
            return results
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return []

def narrow_files(locations: List[Tuple[str, int]], project_root: str, include_parents: int = 0, max_files: int = 100) -> List[str]:
    root = Path(project_root).resolve()
    files = set()
    def _posix(p):
        return str(p).replace(os.sep, "/")
    for abs_file, _ in locations:
        try:
            p = Path(abs_file).resolve()
            rel = p.relative_to(root)
            files.add(_posix(rel))
            for i in range(include_parents):
                if i < len(rel.parents):
                    files.add(_posix(rel.parents[i]))
        except ValueError:
            continue
    return sorted(files)[:max_files]

def probe_and_narrow(project_root: str, symbol_query: str, max_files: int = 100, include_parents: int = 0, max_index_age_days: int = 7) -> List[str]:
    try:
        locations = rg_fallback(project_root, symbol_query)
    except Exception:
        locations = []
    if not locations:
        tags_file = ensure_ctags_index(project_root, max_index_age_days)
        if not tags_file:
            return []
        locations = probe_symbol(tags_file, symbol_query)
    if not locations:
        return []
    return narrow_files(locations, project_root, include_parents, max_files)
