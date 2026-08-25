"""
Utility functions for Tricorder.
"""

import os, fnmatch, time
import sys
from pathlib import Path
from typing import Optional, List
from collections import namedtuple
from dataclasses import dataclass, asdict

try:
    import tiktoken
except ImportError:
    sys.stderr.write("tiktoken is required. Install with: pip install tiktoken\n")
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
# Skip files larger than this (bytes) — likely generated/binary/not source.
# Overridable via env TRICORDER_MAX_SOURCE_FILE_SIZE (bytes). Read at call time
# (see _env_int/_env_float) so tests and runtime tuning don't require re-import.
_MAX_SOURCE_FILE_SIZE = 1024 * 1024
_MAX_SCAN_FILES = 20000
# TC-002: missing envelope pieces — directory-depth, total-byte, and scan-time
# budgets so a hostile repo can't drive unbounded CPU/memory/disk. All
# overridable via env; discovery already early-stops at _MAX_SCAN_FILES.
_MAX_SCAN_DEPTH = 25
_MAX_TOTAL_BYTES = 500 * 1024 * 1024
_MAX_SCAN_TIME_S = 300.0
_BUILTIN_SKIP_DIRS = {'node_modules', '__pycache__', 'venv', 'env', 'build', 'dist', '.tox', '.eggs'}


def _env_int(name: str, default: int) -> int:
    """Read an int env override at call time (TC-002 live tuning)."""
    try:
        return int(os.environ.get(name, default)) or default
    except (TypeError, ValueError):
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default)) or default
    except (TypeError, ValueError):
        return default


def discover_src_files(directory: str, use_gitignore: bool = True, exclude_globs: Optional[List[str]] = None, report: Optional[dict] = None) -> List[str]:
    """Walk a directory and return source files, skipping noise.

    Shared by tricorder_server.find_src_files and Tricorder._discover_files.
    ponytail: one implementation, two callers — no drift.

    TC-002 resource envelope: a single global budget bounds the walk so a
    hostile repo can't drive unbounded CPU/memory/disk. Files are skipped (not
    silently truncated) when they breach a single-file cap, and the walk stops
    cleanly when it hits the file-count / total-byte / directory-depth / time
    limits. If `report` is provided, it is populated with a human-readable
    partial-scan warning instead of raising.

    exclude_globs: optional list of glob patterns matched against the path
    is POSIX-normalized, relative to `directory`. Excludes third-party/
    vendored subtrees from ranking, e.g. exclude_globs=["vendor/**"].
    """
    if report is not None:
        report.clear()
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
    total_bytes = 0
    oversized_skipped = 0
    depth_skipped = 0
    start = time.monotonic()
    root_depth = Path(directory).resolve().parts.__len__()
    # TC-002: read envelope budgets at call time so env overrides (incl. tests) work.
    max_scan_depth = _env_int("TRICORDER_MAX_SCAN_DEPTH", _MAX_SCAN_DEPTH)
    max_total_bytes = _env_int("TRICORDER_MAX_TOTAL_BYTES", _MAX_TOTAL_BYTES)
    max_scan_files = _env_int("TRICORDER_MAX_SCAN_FILES", _MAX_SCAN_FILES)
    max_scan_time_s = _env_float("TRICORDER_MAX_SCAN_TIME_S", _MAX_SCAN_TIME_S)
    max_source_file_size = _env_int("TRICORDER_MAX_SOURCE_FILE_SIZE", _MAX_SOURCE_FILE_SIZE)
    for r, d, f_list in os.walk(directory):
        # TC-002: directory-depth budget.
        depth = Path(r).resolve().parts.__len__() - root_depth
        if depth > max_scan_depth:
            depth_skipped += len(d)
            d[:] = []
            continue
        d[:] = [dn for dn in d if not dn.startswith('.') and dn not in skip_dirs
                and (Path(r).resolve().parts.__len__() - root_depth + 1) <= max_scan_depth]
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
                sz = os.path.getsize(full)
            except OSError:
                sz = 0
            if sz > max_source_file_size:
                oversized_skipped += 1
                continue
            if exclude_globs:
                rel = os.path.relpath(full, directory).replace(os.sep, '/')
                if any(fnmatch.fnmatch(rel, pat) for pat in exclude_globs):
                    continue
            src_files.append(full)
            total_bytes += sz
            # TC-002: total-byte + file-count + scan-time budgets. Return a
            # clean partial result with a warning rather than failing
            # unpredictably. The pre-index probe is required to go deeper.
            hit_limit = None
            if len(src_files) >= max_scan_files:
                hit_limit = f"reached file-count limit ({max_scan_files})"
            elif total_bytes >= max_total_bytes:
                hit_limit = f"reached total-byte limit ({max_total_bytes} bytes)"
            elif (time.monotonic() - start) >= max_scan_time_s:
                hit_limit = f"reached scan-time limit ({max_scan_time_s}s)"
            if hit_limit:
                if report is not None:
                    report["warning"] = (
                        f"Scan completed with limits: skipped {oversized_skipped} "
                        f"oversized files, {depth_skipped} files beyond depth "
                        f"{max_scan_depth}; {hit_limit}."
                    )
                    report["files_considered"] = len(src_files)
                    report["oversized_skipped"] = oversized_skipped
                    report["depth_skipped"] = depth_skipped
                return src_files
    if report is not None:
        report["files_considered"] = len(src_files)
        report["oversized_skipped"] = oversized_skipped
        report["depth_skipped"] = depth_skipped
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
                exclude_globs: Optional[List[str]] = None,
                coverage_pct: Optional[float] = None) -> dict:
    """Budget fields shared by CLI, MCP, and plugin: how many tokens a piece
    of tricorder output costs vs. reading the whole repo.

    full_repo_estimate = tokens of all discoverable source files under
    project_root (canonical definition — a tier-1 map can legitimately cost
    more than reading the repo, so savings_pct clamps at 0, never negative).

    Returns: {"token_estimate": int, "full_repo_estimate": int,
              "savings_pct": float, "coverage_pct": float (optional)}
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
    result = {
        "token_estimate": int(token_estimate),
        "full_repo_estimate": int(full),
        "savings_pct": savings,
    }
    if coverage_pct is not None:
        result["coverage_pct"] = round(coverage_pct, 1)
    return result


# =============================================================================
# Turn-0 probe digest (shared by CLI --probe-digest, Hermes plugin, DSH plugin)
# =============================================================================
# A cheap navigation probe: language tally + rough size. NO map build, NO token
# budget (repo_budget reads/tokenizes every source file — too slow for turn 0
# on a kernel-scale tree). Designed so Hermes and DSH inject byte-identical
# turn-0 content from this one code path.

INJECT_MIN_FILES = 0  # gate removed — probe always injected if code files exist

CODE_EXTENSIONS = {
    ".py": "python", ".rs": "rust", ".c": "c", ".h": "cpp", ".cpp": "cpp",
    ".cc": "cpp", ".cxx": "cpp", ".hpp": "cpp", ".hxx": "cpp",
    ".js": "javascript", ".jsx": "javascript", ".ts": "typescript",
    ".tsx": "typescript", ".go": "go", ".java": "java", ".kt": "kotlin",
    ".scala": "scala", ".rb": "ruby", ".php": "php", ".swift": "swift",
    ".m": "objc", ".cs": "csharp", ".fs": "fsharp",
    ".sh": "bash", ".bash": "bash", ".zsh": "bash",
    ".hcl": "hcl", ".tf": "hcl",
    ".lua": "lua", ".dart": "dart", ".r": "r", ".jl": "julia",
    ".vim": "vim", ".el": "elisp", ".clj": "clojure", ".ex": "elixir",
    ".exs": "elixir", ".erl": "erlang", ".hs": "haskell", ".ml": "ocaml",
    ".nim": "nim", ".zig": "zig", ".v": "verilog", ".sv": "systemverilog",
    ".d": "d", ".sql": "sql", ".cmake": "cmake",
    ".html": "html", ".css": "css", ".scss": "css", ".less": "css",
    ".vue": "javascript", ".svelte": "javascript",
}

_CODE_IGNORE_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv",
                     "target", "build", "dist", ".next", ".nuxt",
                     "vendor", "third_party", ".tricorder"}


def probe_project(project_root: str, exclude_globs: Optional[List[str]] = None) -> dict:
    """Cheap os.walk tally: language counts + total files + rough line estimate.

    No tree-sitter, no parsing, no ranking — just extension tally. Costs
    milliseconds, zero tokens. This is the turn-0 navigation probe, never a
    full map/token scan.

    Returns {"lang_counts": {lang: n}, "total_files": int, "est_lines": int,
             "top_lang": str}.
    """
    root_path = Path(project_root)
    if not root_path.is_dir():
        return {"lang_counts": {}, "total_files": 0, "est_lines": 0, "top_lang": ""}

    globs = exclude_globs or []
    lang_counts: dict = {}
    total_bytes = 0

    for dirpath, dirnames, filenames in os.walk(root_path):
        dirnames[:] = [d for d in dirnames if d not in _CODE_IGNORE_DIRS]
        for fname in filenames:
            rel = os.path.relpath(os.path.join(dirpath, fname), root_path)
            if any(fnmatch.fnmatch(rel, g) for g in globs):
                continue
            ext = os.path.splitext(fname)[1].lower()
            lang = CODE_EXTENSIONS.get(ext)
            if not lang:
                continue
            lang_counts[lang] = lang_counts.get(lang, 0) + 1
            try:
                total_bytes += os.path.getsize(os.path.join(dirpath, fname))
            except OSError:
                pass

    total_files = sum(lang_counts.values())
    # ponytail: ~40 bytes/line average across languages. A probe, not a census.
    est_lines = total_bytes // 40 if total_bytes else 0
    top_lang = max(lang_counts, key=lang_counts.get) if lang_counts else ""
    return {"lang_counts": lang_counts, "total_files": total_files,
            "est_lines": est_lines, "top_lang": top_lang}


def format_probe_digest(probe: dict, project_root: str) -> str:
    """Turn the probe tally into the unified turn-0 digest text.

    Single source of truth: CLI --probe-digest, the Hermes plugin, and the DSH
    plugin all emit this exact string so turn-0 content is identical everywhere.
    Navigation-only — points at MCP tools for depth, never triggers a scan.
    """
    total = probe.get("total_files", 0)
    if not total:
        return ""
    lang_counts = probe.get("lang_counts", {})
    est_lines = probe.get("est_lines", 0)
    top3 = sorted(lang_counts.items(), key=lambda x: -x[1])[:3]
    lang_str = ", ".join(f"{n} {lang}" for lang, n in top3)
    lines_str = f"~{est_lines // 1000}K lines" if est_lines >= 1000 else f"~{est_lines} lines"
    return (
        f"{total} code files ({lang_str}), {lines_str}. "
        "Use the MCP tools (mcp_tricorder_detect/symbols/detail) for targeted "
        "probes, or /tricorder scan / the CLI to build a map on demand. "
        "Do not deep-scan this turn."
    )


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
