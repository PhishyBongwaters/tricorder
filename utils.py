"""
Utility functions for Tricorder.
"""

import os, fnmatch
import sys
from pathlib import Path
from typing import Optional, List
from collections import namedtuple
from dataclasses import dataclass, asdict

try:
    import tiktoken
except ImportError:
    print("Error: tiktoken is required. Install with: pip install tiktoken")
    sys.exit(1)

# Tag namedtuple for storing parsed code definitions and references
Tag = namedtuple("Tag", "rel_fname fname line name kind".split())


@dataclass
class SymbolRecord:
    """Symbol record for search_symbols MCP tool (Milestone 1).

    Flat JSON-serializable record representing a single code symbol
    extracted from tree-sitter AST data. No nested trees.
    """
    name: str
    type: str          # function | class | type | variable | method | import
    file: str          # absolute file path
    line: int          # start line number (1-indexed)
    end_line: int      # end line number (if available)
    signature: str     # function/method signature string
    docstring: str     # docstring content if present
    language: str      # file language (python, typescript, etc.)
    kind: str          # tree-sitter node kind string
    body: str = ""     # code body, first 500 chars (get_symbol_details)
    callers: list = None  # list of {file, line} dicts (get_symbol_details)
    callees: list = None  # list of {name, file, line} dicts (get_symbol_details)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "SymbolRecord":
        return cls(**{k: d[k] for k in cls.__dataclass_fields__})


def count_tokens(text: str, model_name: str = "gpt-4") -> int:
    """Count tokens in text using tiktoken."""
    if not text:
        return 0

    try:
        encoding = tiktoken.encoding_for_model(model_name)
    except KeyError:
        # Fallback for unknown models
        encoding = tiktoken.get_encoding("cl100k_base")

    return len(encoding.encode(text))


def read_text(filename: str, encoding: str = "utf-8", silent: bool = False) -> Optional[str]:
    """Read text from file with error handling."""
    try:
        return Path(filename).read_text(encoding=encoding, errors='ignore')
    except FileNotFoundError:
        if not silent:
            print(f"Error: {filename} not found.")
        return None
    except IsADirectoryError:
        if not silent:
            print(f"Error: {filename} is a directory.")
        return None
    except OSError as e:
        if not silent:
            print(f"Error reading {filename}: {e}")
        return None
    except UnicodeError as e:
        if not silent:
            print(f"Error decoding {filename}: {e}")
        return None
    except Exception as e:
        if not silent:
            print(f"An unexpected error occurred while reading {filename}: {e}")
        return None


_SKIP_EXTS = {'.frag', '.vert', '.inc', '.icns', '.plist', '.entitlements',
              '.cmake.in', '.h.in', '.cpp.in', '.hpp.in'}
_BINARY_MEDIA_EXTS = {
    '.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp', '.ico', '.tif', '.tiff',
    '.mp4', '.mov', '.mkv', '.avi', '.webm', '.mp3', '.wav', '.flac', '.ogg',
    '.pdf', '.svg',
}
# Archive/compressed formats — not source code, never wants to be in a code map.
_ARCHIVE_EXTS = {
    '.tar', '.gz', '.zip', '.bz2', '.xz', '.7z', '.rar', '.tgz', '.tbz2',
}
# Data/asset text formats — not source code, never wants to be in a code map.
_DATA_EXTS = {
    '.milk',          # projectM presets
    '.json', '.xml', '.yaml', '.yml', '.toml', '.ini', '.cfg', '.config',
    '.csv', '.tsv',
    '.md', '.txt', '.rst',  # Documentation, not source code
}
# Skip files larger than this (bytes) — likely generated/binary/not source
_MAX_SOURCE_FILE_SIZE = 1024 * 1024  # 1MB
_BUILTIN_SKIP_DIRS = {'node_modules', '__pycache__', 'venv', 'env', 'build', 'dist', '.tox', '.eggs'}


def discover_src_files(directory: str, use_gitignore: bool = True, exclude_globs: Optional[List[str]] = None) -> List[str]:
    """Walk a directory and return source files, skipping noise.

    Shared by tricorder_server.find_src_files and Tricorder._discover_files.
    ponytail: one implementation, two callers — no drift.

    exclude_globs: optional list of glob patterns matched against the path
    (as POSIX-normalized, relative to `directory`). Excludes third-party/
    vendored subtrees from ranking, e.g. exclude_globs=["vendor/**"].
    """
    if not os.path.isdir(directory):
        return [directory] if os.path.isfile(directory) else []
    # Find git root for .gitignore parsing
    gitignore_dirs: set = set()
    if use_gitignore:
        git_root = None
        p = Path(directory).resolve()
        while p != p.parent:
            if (p / '.git').exists():
                git_root = str(p)
                break
            p = p.parent
        gitignore_dirs = parse_gitignore(git_root or directory)
    skip_dirs = gitignore_dirs | _BUILTIN_SKIP_DIRS | {'vendor'}
    src_files = []
    for r, d, f_list in os.walk(directory):
        d[:] = [dn for dn in d if not dn.startswith('.') and dn not in skip_dirs]
        for f in f_list:
            if f.startswith('.'):
                continue
            # Case-insensitive ext check: .Jpg slides past .jpg otherwise.
            low = f.lower()
            if any(low.endswith(ext) for ext in _SKIP_EXTS | _BINARY_MEDIA_EXTS | _ARCHIVE_EXTS | _DATA_EXTS):
                continue
            full = os.path.join(r, f)
            # Skip large files (likely generated/binary/not source)
            try:
                if os.path.getsize(full) > _MAX_SOURCE_FILE_SIZE:
                    continue
            except OSError:
                pass
            if exclude_globs:
                rel = os.path.relpath(full, directory).replace(os.sep, '/')
                if any(fnmatch.fnmatch(rel, pat) for pat in exclude_globs):
                    continue
            src_files.append(full)
    return src_files


def parse_gitignore(root: str) -> set:
    """Parse .gitignore from repo root and return a set of directory patterns to skip.

    Handles: bare dir names (match any depth), trailing slashes, negation (!),
    comments, and blank lines. Does NOT handle complex fnmatch edge cases
    (leading slashes, double-asterisks) — good enough for 99% of repos.

    ponytail: returns a set of directory basenames. os.walk filters dirs[:]
    against this set. If a pattern is file-only (e.g. '*.log'), it's ignored
    here — file-level filtering is handled by _SKIP_EXTS.
    """
    patterns: set[str] = set()
    gitignore = Path(root) / ".gitignore"
    if not gitignore.exists():
        return patterns
    try:
        for line in gitignore.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            # Negation: skip the pattern
            if line.startswith("!"):
                continue
            # Strip trailing slash (dir indicator)
            pattern = line.rstrip("/")
            # Only care about directory-level patterns (no dots, no wildcards)
            # — these are the common build dirs like "build", "dist", ".venv"
            if not pattern or "*" in pattern or "." in pattern:
                continue
            patterns.add(pattern)
    except OSError:
        pass
    return patterns


def detect_lang(fname: str) -> Optional[str]:
    """Detect language for a source file, overriding .h to cpp.

    grep-ast maps .h -> c, but most modern .h files are C++ (classes,
    namespaces, templates). The cpp tree-sitter grammar is a strict
    superset of C — it parses C code fine and the cpp query file has
    all the C patterns plus class/method patterns.

    ponytail: always map .h to cpp. Ceiling: a pure-C project's .h
    files would be parsed with the cpp query — harmless, the C
    patterns (struct, function, enum, typedef) are all in cpp-tags.scm.
    """
    from grep_ast import filename_to_lang
    lang = filename_to_lang(fname)
    if lang == "c" and fname.endswith((".h", ".H")):
        return "cpp"
    return lang


def repo_budget(project_root: str, token_estimate: int,
                model_name: str = "gpt-4",
                exclude_globs: Optional[List[str]] = None) -> dict:
    """Budget fields shared by CLI, MCP, and plugin: how many tokens a piece
    of tricorder output costs vs. reading the whole repo.

    full_repo_estimate = tokens of all discoverable source files under
    project_root (canonical definition — a tier-1 map can legitimately cost
    more than reading the repo, so savings_pct clamps at 0, never negative).

    Returns: {"token_estimate": int, "full_repo_estimate": int,
              "savings_pct": float}
    """
    files = discover_src_files(project_root, use_gitignore=True,
                               exclude_globs=exclude_globs)
    full = 0
    for f in files:
        try:
            txt = read_text(f, silent=True)
            if txt:
                full += count_tokens(txt, model_name)
        except Exception:
            continue
    if not full or token_estimate <= 0:
        savings = 0.0
    else:
        savings = round(max(0.0, 1 - token_estimate / full) * 100, 1)
    return {
        "token_estimate": int(token_estimate),
        "full_repo_estimate": int(full),
        "savings_pct": savings,
    }


# =============================================================================
# Graph Query DSL Parser (M0.10)
# =============================================================================

@dataclass
class QueryModifiers:
    """Modifiers for a single traversal step."""
    depth: int = 1
    exclude_globs: List[str] = None
    include_globs: List[str] = None
    symbol_type: Optional[str] = None  # function, class, method, variable
    limit: int = 100

    def __post_init__(self):
        if self.exclude_globs is None:
            self.exclude_globs = []
        if self.include_globs is None:
            self.include_globs = []


@dataclass
class TraversalStep:
    """A single traversal step in the query."""
    kind: str  # "callers", "callees", "refs", "defs"
    target: str  # symbol name to start from
    modifiers: QueryModifiers


@dataclass
class ParsedQuery:
    """Complete parsed query with multiple chained steps."""
    steps: List[TraversalStep]


def parse_query_dsl(dsl: str) -> ParsedQuery:
    """Parse graph query DSL into structured form.

    Grammar:
        query := traversal (pipe traversal)*
        traversal := kind '(' target ')' modifiers?
        kind := "callers" | "callees" | "refs" | "defs"
        target := quoted string (single or double quotes)
        modifiers := (modifier)*
        modifier := "depth=" INT | "exclude=" GLOB | "include=" GLOB
                  | "type=" ("function"|"class"|"method"|"variable") | "limit=" INT
        pipe := "|"

    Examples:
        "callers('authenticate') depth=2"
        "callees('main') depth=1 exclude=tests/**"
        "refs('Config') type=class limit=50"
        "callers('foo') | callees('bar') depth=3"
    """
    if not dsl or not dsl.strip():
        raise ValueError("Empty query string")

    steps = []
    # Split by pipe for chained traversals
    traversal_strs = [s.strip() for s in dsl.split('|')]

    for trav_str in traversal_strs:
        if not trav_str:
            continue

        # Match kind and target: kind('target') or kind("target")
        match = re.match(r'^(callers|callees|refs|defs)\s*\(\s*([\'"])(.*?)\2\s*\)(.*)$', trav_str)
        if not match:
            raise ValueError(f"Invalid traversal syntax: {trav_str}")

        kind, _, target, modifiers_str = match.groups()

        # Parse modifiers
        mods = QueryModifiers()

        # depth=N
        depth_match = re.search(r'depth\s*=\s*(\d+)', modifiers_str)
        if depth_match:
            mods.depth = int(depth_match.group(1))

        # exclude=glob (can be multiple, comma-separated or repeated)
        # Match exclude=value where value can contain commas if quoted, or single values
        exclude_str = re.search(r'exclude\s*=\s*([^\s|]+)', modifiers_str)
        if exclude_str:
            # Split by comma but respect quoted strings
            val = exclude_str.group(1)
            # Simple split by comma for now - handles tests/**,vendor/**
            mods.exclude_globs = [g.strip() for g in val.split(',') if g.strip()]

        # include=glob
        include_str = re.search(r'include\s*=\s*([^\s|]+)', modifiers_str)
        if include_str:
            val = include_str.group(1)
            mods.include_globs = [g.strip() for g in val.split(',') if g.strip()]

        # type=function|class|method|variable
        type_match = re.search(r'type\s*=\s*(function|class|method|variable)', modifiers_str)
        if type_match:
            mods.symbol_type = type_match.group(1)

        # limit=N
        limit_match = re.search(r'limit\s*=\s*(\d+)', modifiers_str)
        if limit_match:
            mods.limit = int(limit_match.group(1))

        steps.append(TraversalStep(kind=kind, target=target, modifiers=mods))

    return ParsedQuery(steps=steps)


import re
