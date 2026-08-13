"""
Utility functions for RepoMap.
"""

import os
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
_BUILTIN_SKIP_DIRS = {'node_modules', '__pycache__', 'venv', 'env', 'build', 'dist', '.tox', '.eggs'}


def discover_src_files(directory: str, use_gitignore: bool = True) -> List[str]:
    """Walk a directory and return source files, skipping noise.

    Shared by repomap_server.find_src_files and RepoMap._discover_files.
    ponytail: one implementation, two callers — no drift.
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
    skip_dirs = gitignore_dirs | _BUILTIN_SKIP_DIRS
    src_files = []
    for r, d, f_list in os.walk(directory):
        d[:] = [dn for dn in d if not dn.startswith('.') and dn not in skip_dirs]
        for f in f_list:
            if f.startswith('.'):
                continue
            if any(f.endswith(ext) for ext in _SKIP_EXTS):
                continue
            src_files.append(os.path.join(r, f))
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
