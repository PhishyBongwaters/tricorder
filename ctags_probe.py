#!/usr/bin/env python3
"""
ctags probe — fast symbol index for repo filtering before tree-sitter.
"""

import hashlib
import json
import subprocess
import os
import sys
import time
from pathlib import Path
from typing import List, Tuple, Optional
import fnmatch

# safe_write lives in utils; reuse it (contains the cache-root invariant).
from utils import safe_write  # noqa: E402

CTAGS_MAX_SOURCE_FILES = 20000


# =============================================================================
# Language Registry — single source of truth for supported languages
# =============================================================================
# This registry maps language keys to their properties:
# - ctags_name: name used in ctags --languages=...
# - tree_sitter_key: key used in tree-sitter-language-pack / grep-ast
# - extensions: file extensions (used for rg fallback, etc.)
# - scm_query_file: scm query filename in queries/ directory
#
# Keep in sync with tree-sitter-language-pack supported languages and
# the scm queries in queries/tree-sitter-language-pack/ and queries/tree-sitter-languages/
#
LANGUAGE_REGISTRY = {
    "python": {
        "ctags_name": "Python",
        "tree_sitter_key": "python",
        "extensions": [".py"],
        "scm_query": "python-tags.scm",
    },
    "javascript": {
        "ctags_name": "JavaScript",
        "tree_sitter_key": "javascript",
        "extensions": [".js", ".jsx"],
        "scm_query": "javascript-tags.scm",
    },
    "typescript": {
        "ctags_name": "TypeScript",
        "tree_sitter_key": "typescript",
        "extensions": [".ts", ".tsx"],
        "scm_query": "typescript-tags.scm",
    },
    "c": {
        "ctags_name": "C",
        "tree_sitter_key": "c",
        "extensions": [".c", ".h"],
        "scm_query": "c-tags.scm",
    },
    "cpp": {
        "ctags_name": "C++",
        "tree_sitter_key": "cpp",
        "extensions": [".cpp", ".cc", ".cxx", ".hpp", ".hxx", ".h"],
        "scm_query": "cpp-tags.scm",
    },
    "java": {
        "ctags_name": "Java",
        "tree_sitter_key": "java",
        "extensions": [".java"],
        "scm_query": "java-tags.scm",
    },
    "go": {
        "ctags_name": "Go",
        "tree_sitter_key": "go",
        "extensions": [".go"],
        "scm_query": "go-tags.scm",
    },
    "rust": {
        "ctags_name": "Rust",
        "tree_sitter_key": "rust",
        "extensions": [".rs"],
        "scm_query": "rust-tags.scm",
    },
    "swift": {
        "ctags_name": "Swift",
        "tree_sitter_key": "swift",
        "extensions": [".swift"],
        "scm_query": "swift-tags.scm",
    },
    "kotlin": {
        "ctags_name": "Kotlin",
        "tree_sitter_key": "kotlin",
        "extensions": [".kt", ".kts"],
        "scm_query": "kotlin-tags.scm",
    },
    "ruby": {
        "ctags_name": "Ruby",
        "tree_sitter_key": "ruby",
        "extensions": [".rb"],
        "scm_query": "ruby-tags.scm",
    },
    "php": {
        "ctags_name": "PHP",
        "tree_sitter_key": "php",
        "extensions": [".php"],
        "scm_query": "php-tags.scm",
    },
    "c_sharp": {
        "ctags_name": "C#",
        "tree_sitter_key": "c_sharp",
        "extensions": [".cs"],
        "scm_query": "c_sharp-tags.scm",
    },
    "shell": {
        "ctags_name": "Shell",
        "tree_sitter_key": "shell",
        "extensions": [".sh", ".bash", ".zsh"],
        "scm_query": "shell-tags.scm",
    },
    "lua": {
        "ctags_name": "Lua",
        "tree_sitter_key": "lua",
        "extensions": [".lua"],
        "scm_query": "lua-tags.scm",
    },
    "perl": {
        "ctags_name": "Perl",
        "tree_sitter_key": "perl",
        "extensions": [".pl", ".pm"],
        "scm_query": "perl-tags.scm",
    },
    "sql": {
        "ctags_name": "SQL",
        "tree_sitter_key": "sql",
        "extensions": [".sql"],
        "scm_query": "sql-tags.scm",
    },
    "html": {
        "ctags_name": "HTML",
        "tree_sitter_key": "html",
        "extensions": [".html", ".htm"],
        "scm_query": "html-tags.scm",
    },
    "css": {
        "ctags_name": "CSS",
        "tree_sitter_key": "css",
        "extensions": [".css", ".scss", ".less"],
        "scm_query": "css-tags.scm",
    },
    "json": {
        "ctags_name": "JSON",
        "tree_sitter_key": "json",
        "extensions": [".json"],
        "scm_query": "json-tags.scm",
    },
    "yaml": {
        "ctags_name": "YAML",
        "tree_sitter_key": "yaml",
        "extensions": [".yaml", ".yml"],
        "scm_query": "yaml-tags.scm",
    },
    "toml": {
        "ctags_name": "TOML",
        "tree_sitter_key": "toml",
        "extensions": [".toml"],
        "scm_query": "toml-tags.scm",
    },
    "xml": {
        "ctags_name": "XML",
        "tree_sitter_key": "xml",
        "extensions": [".xml"],
        "scm_query": "xml-tags.scm",
    },
    "markdown": {
        "ctags_name": "Markdown",
        "tree_sitter_key": "markdown",
        "extensions": [".md"],
        "scm_query": "markdown-tags.scm",
    },
    # Tree-sitter only (no ctags support yet):
    # "zig": {"ctags_name": None, "tree_sitter_key": "zig", "extensions": [".zig"], "scm_query": "zig-tags.scm"},
    # "r": {"ctags_name": None, "tree_sitter_key": "r", "extensions": [".r"], "scm_query": "r-tags.scm"},
    # etc.
}


def get_ctags_languages() -> List[str]:
    """Get list of ctags-supported language names."""
    return [info["ctags_name"] for info in LANGUAGE_REGISTRY.values() if info["ctags_name"]]


def get_tree_sitter_languages() -> List[str]:
    """Get list of tree-sitter-supported language keys."""
    return [info["tree_sitter_key"] for info in LANGUAGE_REGISTRY.values()]


def get_language_extensions(lang_key: str) -> List[str]:
    """Get file extensions for a language key."""
    return LANGUAGE_REGISTRY.get(lang_key, {}).get("extensions", [])


def get_scm_query_for_lang(lang_key: str) -> Optional[str]:
    """Get SCM query filename for a language key."""
    return LANGUAGE_REGISTRY.get(lang_key, {}).get("scm_query")


def get_ctags_name(lang_key: str) -> Optional[str]:
    """Get ctags language name for a tree-sitter language key."""
    return LANGUAGE_REGISTRY.get(lang_key, {}).get("ctags_name")


def _get_repo_hash(project_root: str) -> str:
    """Generate a stable hash for the repository root path."""
    return hashlib.sha256(Path(project_root).resolve().as_posix().encode()).hexdigest()[:16]


def _get_tags_cache_path(project_root: str) -> Path:
    """Get the external cache path for the ctags index."""
    from utils import get_cache_root, safe_write
    cache_root = get_cache_root()
    if cache_root is None:
        # No writable cache root -- return a path under the project root
        # as a last resort (caller should handle the failure case)
        cache_dir = Path(project_root) / ".tricorder" / "indexes" / _get_repo_hash(project_root)
    else:
        cache_dir = cache_root / "indexes" / _get_repo_hash(project_root)
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir / "tags"


def _get_meta_cache_path(project_root: str) -> Path:
    """Get the external cache path for the ctags index metadata."""
    from utils import get_cache_root, safe_write
    cache_root = get_cache_root()
    if cache_root is None:
        cache_dir = Path(project_root) / ".tricorder" / "indexes" / _get_repo_hash(project_root)
    else:
        cache_dir = cache_root / "indexes" / _get_repo_hash(project_root)
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir / "tags.meta.json"


def _get_git_commit(project_root: str) -> Optional[str]:
    """Get the current git commit hash for the repository."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=project_root, capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return None


def _read_tags_meta(meta_path: Path) -> Optional[dict]:
    """Read and parse the tags metadata file."""
    try:
        if meta_path.exists():
            return json.loads(meta_path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return None


def _write_tags_meta(meta_path: Path, meta: dict) -> None:
    """Write the tags metadata file (best-effort; escape paths raise)."""
    try:
        safe_write(meta_path, json.dumps(meta))
    except OSError:
        pass


def _is_meta_stale(meta: dict, project_root: str, ctags_excludes: List[str], max_age_days: int) -> bool:
    """Check if the ctags index metadata is stale.
    
    Invalidates on:
    - Missing or malformed metadata
    - Git commit mismatch (if git available)
    - File count mismatch (using same discovery logic)
    - Age exceeds max_age_days
    """
    # Check metadata exists and has required fields
    if not meta or "git_commit" not in meta or "file_count" not in meta or "generated" not in meta:
        return True
    
    # Check age
    age_days = (time.time() - meta["generated"]) / 86400
    if age_days > max_age_days:
        return True
    
    # Check git commit if available
    current_commit = _get_git_commit(project_root)
    if current_commit and meta["git_commit"] != current_commit:
        return True
    
    # Check file count using same discovery logic
    current_count = _count_source_files(project_root, exclude_globs=ctags_excludes)
    if meta["file_count"] != current_count:
        return True
    
    return False


def _count_source_files(project_root: str, exclude_globs: Optional[List[str]] = None) -> int:
    """Count discoverable source files using shared discovery logic.
    
    Uses the same filtering as tricorder: gitignore, built-in skip dirs,
    vendor/, binary/media/archive extensions, and optional exclude_globs.
    """
    # Import locally to avoid circular dependency
    from utils import discover_src_files
    
    files = discover_src_files(project_root, use_gitignore=True, exclude_globs=exclude_globs)
    return len(files)


def _run_ctags(project_root: str, tags_file: Path) -> bool:
    # Exclude patterns matching the ctags command below (converted from ctags --exclude format)
    ctags_excludes = [
        "*.min.js", "*.min.css", "vendor/**", "third_party/**",
        ".git/**", "build/**", "dist/**", "node_modules/**",
        "__pycache__/**", "*.pyc",
    ]
    if _count_source_files(project_root, exclude_globs=ctags_excludes) > CTAGS_MAX_SOURCE_FILES:
        print(f"[ctags_probe] SKIP index: >{CTAGS_MAX_SOURCE_FILES} source files in {project_root} (rg fallback only)", file=sys.stderr)
        return False
    
    # Use language registry for ctags --languages
    ctags_langs = get_ctags_languages()
    exclude = ["--exclude=" + pat for pat in ctags_excludes]
    cmd = [
        "ctags", "-R",
        "--languages=" + ",".join(ctags_langs),
        "--fields=+n", "-f", str(tags_file), *exclude, project_root,
    ]
    try:
        subprocess.run(cmd, capture_output=True, timeout=120, check=True)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        return False


def ensure_ctags_index(project_root: str, max_age_days: int = 7) -> Optional[Path]:
    tags_file = _get_tags_cache_path(project_root)
    meta_file = _get_meta_cache_path(project_root)
    
    # Exclude patterns matching the ctags command
    ctags_excludes = [
        "*.min.js", "*.min.css", "vendor/**", "third_party/**",
        ".git/**", "build/**", "dist/**", "node_modules/**",
        "__pycache__/**", "*.pyc",
    ]
    
    # Check if existing index is valid using metadata
    if tags_file.exists() and meta_file.exists():
        # Refuse oversized indexes: a sane per-repo tags index is a few MB.
        if tags_file.stat().st_size > 100 * 1024 * 1024:
            print(f"[ctags_probe] SKIP huge existing index {tags_file} "
                  f"({tags_file.stat().st_size // (1024*1024)}MB); rg-only",
                  file=sys.stderr)
            return None
        
        meta = _read_tags_meta(meta_file)
        if meta and not _is_meta_stale(meta, project_root, ctags_excludes, max_age_days):
            return tags_file
    
    # Generate new index
    if _run_ctags(project_root, tags_file):
        # Write metadata for future invalidation
        git_commit = _get_git_commit(project_root)
        file_count = _count_source_files(project_root, exclude_globs=ctags_excludes)
        meta = {
            "git_commit": git_commit,
            "file_count": file_count,
            "generated": time.time(),
        }
        _write_tags_meta(meta_file, meta)
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
    # -l (files-with-matches): only file paths are emitted, so there is no
    # path:line:content to parse. Parsing -n output is ambiguous on Windows
    # (drive-letter colon in the path; content often contains colons too) and
    # used to leak e.g. 'sched.h:371: *   dl_se' into the narrowed file set.
    # line number is unused downstream (narrow_files reads only [0]).
    cmd = ["rg", "-l", "--no-heading", "-w", "-g", "*.c", "-g", "*.h", "-g", "*.cpp", "-g", "*.hpp", "-g", "*.cc", "-g", "*.py", "-g", "*.js", "-g", "*.ts", "-g", "*.go", "-g", "*.rs", "-g", "*.java", "-g", "*.rb", "-g", "*.php", "-g", "*.sh", "-g", "*.erl", "-g", "*.ex", "-g", "*.kt", "-g", "*.swift"]
    if lang:
        cmd += ["-t", lang]
    cmd += [symbol, project_root]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=30, check=False)
        if r.returncode == 0:
            return [(p.rstrip("\r"), 0) for p in r.stdout.splitlines() if p.strip()]
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
