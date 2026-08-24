#!/usr/bin/env python3
"""
ctags probe — fast symbol index for repo filtering before tree-sitter.

Usage:
    from ctags_probe import ensure_ctags_index, probe_symbol, narrow_files

    # One-time index (cached at repo_root/tags)
    tags_file = ensure_ctags_index("/path/to/repo")

    # Fast symbol lookup
    locations = probe_symbol(tags_file, "PCM::AddToBuffer")

    # Narrow file list to only those containing the symbol
    relevant_files = narrow_files(locations, "/path/to/repo")
"""

import subprocess
import os
import sys
import time
from pathlib import Path
from typing import List, Tuple, Optional
import fnmatch


def _run_ctags(project_root: str, tags_file: Path) -> bool:
    """Run universal-ctags on project. Returns True on success."""
    # Exclude common vendored/large dirs to keep index fast
    exclude = [
        "--exclude=*.min.js",
        "--exclude=*.min.css",
        "--exclude=vendor/**",
        "--exclude=third_party/**",
        "--exclude=.git/**",
        "--exclude=build/**",
        "--exclude=dist/**",
        "--exclude=node_modules/**",
        "--exclude=__pycache__/**",
        "--exclude=*.pyc",
    ]
    cmd = [
        "ctags", "-R",
        # Single argument — splitting the language list across two CLI tokens
        # makes ctags treat the second as a file name.
        "--languages=C,C++,Python,JavaScript,TypeScript,Go,Rust,Java,Kotlin,Swift,PHP,Ruby,Perl,Lua,Shell,SQL,HTML,CSS,JSON,YAML,TOML,XML,Markdown",
        "--fields=+n",          # line numbers (classic format: line:N in the ;" tail)
        "-f", str(tags_file),
        *exclude,
        project_root,
    ]
    # NOTE: default (classic) tags format is used — emits one line per symbol as
    #   name\tfile\t/pattern/;"\ttype...\tline:<N>
    # probe_symbol() parses this exact shape. Do NOT switch to etags format
    # (name<DEL>file<0x01>line,char) — that needs a different parser.
    try:
        # 120s timeout; ctags on linux kernel (~70k files) takes ~20s
        subprocess.run(cmd, capture_output=True, timeout=120, check=True)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        return False


def ensure_ctags_index(project_root: str, max_age_days: int = 7) -> Optional[Path]:
    """
    Ensure ctags index exists and is fresh. Returns tags file path or None.
    
    Index location: <project_root>/tags (standard ctags location)
    """
    tags_file = Path(project_root) / "tags"
    
    # Check if exists and fresh
    if tags_file.exists():
        age_days = (time.time() - tags_file.stat().st_mtime) / 86400
        if age_days <= max_age_days:
            return tags_file
    
    # Build index
    print(f"[ctags_probe] Building ctags index for {project_root}...")
    if _run_ctags(project_root, tags_file):
        print(f"[ctags_probe] Index built: {tags_file}")
        return tags_file
    
    print("[ctags_probe] ctags failed or not installed", file=sys.stderr)
    return None


def probe_symbol(tags_file: Path, symbol: str) -> List[Tuple[str, int]]:
    """
    Look up symbol in ctags file. Returns [(file, line), ...].

    ctags stores the BASE symbol name in the first column (namespace/class
    goes in the `class:` field), so 'PCM::AddToBuffer' must be looked up as
    'AddToBuffer'. Strip any trailing '-qualified' prefix before matching.
    """
    if not tags_file.exists():
        return []
    
    # ctags indexes the base name; strip a leading 'Namespace::' prefix.
    lookup = symbol.rsplit("::", 1)[-1].rsplit(".", 1)[-1]
    
    results = []
    try:
        with open(tags_file, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('!'):
                    continue
                # classic format: name\\tfile\\tpattern;\\"\\tkind\\tline:N
                if line.startswith(lookup + "\t") or f"\t{lookup}\t" in line:
                    parts = line.split("\t")
                    if len(parts) >= 2:
                        file_path = parts[1]
                        # Extract line number from line:<num> field
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
    """Fallback to ripgrep if ctags misses the symbol."""
    cmd = ["rg", "-n", "--no-heading"]
    if lang:
        cmd += ["-t", lang]
    cmd += [symbol, project_root]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=30, check=False)
        if r.returncode == 0:
            results = []
            for line in r.stdout.strip().splitlines():
                # rg -n output: <path>:<line>:<content>. Windows paths contain
                # colons (C:), so split from the RIGHT to keep the full path.
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


def narrow_files(
    locations: List[Tuple[str, int]],
    project_root: str,
    include_parents: int = 0,
    max_files: int = 100
) -> List[str]:
    """
    Convert symbol locations to relative file list for tree-sitter.
    
    Args:
        locations: [(abs_file, line), ...]
        project_root: repo root for relativizing
        include_parents: also include N parent dirs of each match
        max_files: cap on returned files
    """
    root = Path(project_root).resolve()
    files = set()
    
    def _posix(p):
        # Use forward slashes for relative paths — matches tree-sitter scan
        # conventions and is cross-platform.
        return str(p).replace(os.sep, "/")

    for abs_file, _ in locations:
        try:
            p = Path(abs_file).resolve()
            rel = p.relative_to(root)
            files.add(_posix(rel))
            # Include parent dirs if requested. rel.parents[0] is the file's
            # containing dir; index N is N levels up.
            for i in range(include_parents):
                if i < len(rel.parents):
                    files.add(_posix(rel.parents[i]))
        except ValueError:
            # File outside project root
            continue
    
    # Sort for deterministic output
    sorted_files = sorted(files)
    return sorted_files[:max_files]


def probe_and_narrow(
    project_root: str,
    symbol_query: str,
    max_files: int = 100,
    include_parents: int = 0,
    max_index_age_days: int = 7
) -> List[str]:
    """
    One-shot: ensure index → probe symbol → narrow file list.
    
    Returns relative file paths ready for tree-sitter scan.
    Empty list = fallback to normal auto-discovery.
    """
    tags_file = ensure_ctags_index(project_root, max_index_age_days)
    if not tags_file:
        return []
    
    locations = probe_symbol(tags_file, symbol_query)
    if not locations:
        # Try rg fallback
        locations = rg_fallback(project_root, symbol_query)
    
    if not locations:
        return []
    
    return narrow_files(locations, project_root, include_parents, max_files)


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 3:
        print("Usage: ctags_probe.py <project_root> <symbol_query> [max_files]")
        sys.exit(1)
    
    root = sys.argv[1]
    symbol = sys.argv[2]
    max_f = int(sys.argv[3]) if len(sys.argv) > 3 else 100
    
    files = probe_and_narrow(root, symbol, max_files=max_f)
    if files:
        for f in files:
            print(f)
    else:
        print("[]", file=sys.stderr)
        sys.exit(1)