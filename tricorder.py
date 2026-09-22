#!/usr/bin/env python3
"""
Standalone Tricorder Tool

A command-line tool that generates a "map" of a software repository,
highlighting important files and definitions based on their relevance.
Uses Tree-sitter for parsing and PageRank for ranking importance.
"""

import argparse
import hashlib
import os
import sys
from pathlib import Path
from typing import List, Optional

# Bind the script's own dir ahead of sys.path so `from utils import ...` always
# resolves to THIS project's modules, not a same-named module in another
# venv/site-packages (e.g. the Hermes agent's own utils.py when tricorder is
# launched through an editable install that shares a process's sys.path).
sys.path.insert(0, str(Path(__file__).resolve().parent))
from utils import count_tokens, read_text, Tag, parse_gitignore, discover_src_files, repo_budget, probe_project, format_probe_digest, INJECT_MIN_FILES, safe_write, get_cache_root, db_root_matches, _db_writable, read_only_connect, resolve_or_none, stat_fingerprint
from scm import get_scm_fname
from importance import filter_important_files
from core import Tricorder
from database import DBStore, drop_mapped_files
from ctags_probe import probe_and_narrow


def find_git_root(base: str) -> Optional[str]:
    """Search upward from base for .git/ and return the repo root."""
    p = Path(base).resolve()
    while p != p.parent:
        if (p / '.git').exists():
            return str(p)
        p = p.parent
    return None


def _canonical_db_for(root: str) -> Optional[str]:
    """Index DB for root: <cache>/db/<name>.db, keyed by directory basename.

    State is never kept inside the scanned repo — the canonical DB always
    lives in the tricorder workspace cache root (TRICORDER_CACHE_HOME or
    <workspace>/.tricorder/). Mirrors tricorder_server._canonical_db_for so
    the CLI --diff mode sees the same index the MCP server uses. None if
    no DB exists yet.

    Basename collisions in the shared cache (same folder name, different
    repo) are rejected via db_root_matches — a mismatched DB reports as
    absent rather than corrupting the delta map."""
    name = f"{Path(root).name}.db"
    cand = get_cache_root() / "db" / name
    try:
        if cand.exists() and db_root_matches(str(cand), root):
            return str(cand)
    except Exception:
        pass
    return None


def find_src_files(directory: str, exclude_globs: Optional[List[str]] = None) -> List[str]:
    """Find source files in a directory (delegates to shared discover_src_files)."""
    return discover_src_files(directory, use_gitignore=True, exclude_globs=exclude_globs)


def compute_signature(root: str, exclude_globs: Optional[List[str]] = None) -> str:
    """Stat-based signature: path + size + mtime_ns per source file, sha256'd.

    ponytail: stat-based (path+size+mtime), not content hash.
    Misses: content changed but size+mtime_ns unchanged (practically never
    on real filesystems — ns resolution since review round 16).
    Upgrade path: content hash if this ever bites.
    """
    h = hashlib.sha256()
    files = sorted(discover_src_files(root, use_gitignore=True,
                                       exclude_globs=exclude_globs))
    for fpath in files:
        try:
            st = os.stat(fpath)
            h.update(f"{fpath}:{st.st_size}:{st.st_mtime_ns}".encode())
        except OSError:
            continue
    return h.hexdigest()[:16]


def tool_output(*messages):
    """Print informational messages."""
    print(*messages, file=sys.stdout)


def tool_warning(message):
    """Print warning messages."""
    print(f"Warning: {message}", file=sys.stderr)


def tool_error(message):
    """Print error messages."""
    print(f"Error: {message}", file=sys.stderr)


def _effective_db_path(args, root_path, *, for_write=False) -> Optional[str]:
    """Resolve the DB path for this run.

    Explicit --db-path wins (unless --no-db). Otherwise fall back to the
    canonical index DB (--init canonical, else shared-cache) so the CLI
    map path resumes the same index the MCP server uses and --diff sees.
    None when no DB exists yet (historical in-memory default preserved
    for fresh repos); --no-db always forces None.

    for_write: map scans write file_state/tags, so an existing-but-
    unwritable canonical DB is skipped — degrading to in-memory beats
    crashing on the first write. Readers (--diff) keep a read-only DB:
    diff_against_index never updates the index.
    """
    if args.no_db:
        return None
    if args.db_path:
        return args.db_path
    cand = _canonical_db_for(str(root_path))
    if cand and for_write and not _db_writable(cand):
        return None
    return cand


def _unwritable_canonical_warning(args, root_path, scan_db_path) -> Optional[str]:
    """Warning text when the map path degraded to in-memory because the
    canonical DB exists but isn't writable. None when nothing degraded."""
    if (not args.diff and not args.no_db and not args.db_path
            and scan_db_path is None and _canonical_db_for(str(root_path))):
        return ("Canonical DB exists but is not writable; this run scans "
                "in-memory (no resumption).")
    return None


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Generate a repository map showing important code structures.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s .                    # Map current directory
  %(prog)s src/ --map-tokens 2048  # Map src/ with 2048 token limit
  %(prog)s file1.py file2.py    # Map specific files
  %(prog)s --chat-files main.py --other-files src/  # Specify chat vs other files
        """
    )

    parser.add_argument(
        "paths",
        nargs="*",
        help="Files or directories to include in the map"
    )

    parser.add_argument(
        "--root",
        default=".",
        help="Repository root directory (default: current directory)"
    )

    parser.add_argument(
        "--map-tokens",
        type=int,
        default=8192,
        help="Maximum tokens for the generated map (default: 8192)"
    )

    parser.add_argument(
        "--chat-files",
        nargs="*",
        help="Files currently being edited (given higher priority)"
    )

    parser.add_argument(
        "--other-files",
        nargs="*",
        help="Other files to consider for the map"
    )

    parser.add_argument(
        "--mentioned-files",
        nargs="*",
        help="Files explicitly mentioned (given higher priority)"
    )

    parser.add_argument(
        "--mentioned-idents",
        nargs="*",
        help="Identifiers explicitly mentioned (given higher priority)"
    )

    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose output"
    )

    parser.add_argument(
        "--full",
        action="store_true",
        help="Emit the full map regardless of token budget (disables truncation)"
    )

    parser.add_argument(
        "--model",
        default="gpt-4",
        help="Model name for token counting (default: gpt-4)"
    )

    parser.add_argument(
        "--max-context-window",
        type=int,
        help="Maximum context window size"
    )

    parser.add_argument(
        "--force-refresh",
        action="store_true",
        help="Force refresh of caches"
    )

    parser.add_argument(
        "--exclude-unranked",
        action="store_true",
        help="Exclude files with Page Rank 0 from the map"
    )

    parser.add_argument(
        "--output",
        help="Write map to file instead of stdout"
    )

    parser.add_argument(
        "--format",
        choices=["text", "json"],
        default="text",
        help="Output format (default: text)"
    )

    parser.add_argument(
        "--diff", "--since",
        action="store_true",
        help="Show what changed since the last scan (added/modified/deleted "
             "files plus tags for changed files) instead of generating a map. "
             "Read-only; honors --format. --since is an alias for --diff."
    )

    parser.add_argument(
        "--detect",
        metavar="QUERY",
        default=None,
        help="Search identifier definitions/references for QUERY and exit "
             "(MCP tricorder_detect equivalent, subset of its options). Honors --format."
    )

    parser.add_argument(
        "--symbols",
        metavar="QUERY",
        default=None,
        help="Search code symbols for QUERY and exit "
             "(MCP tricorder_symbols equivalent, subset of its options). Honors --format."
    )

    parser.add_argument(
        "--max-results",
        type=int,
        default=10,
        help="Maximum results for --detect/--symbols (default: 10)"
    )

    parser.add_argument(
        "--max-tokens",
        type=int,
        default=None,
        help="Token budget for --detect/--symbols responses: trims per-hit "
             "context first (identity survives), then lowest-ranked hits. "
             "Unset (default) is unbounded."
    )

    parser.add_argument(
        "--top",
        type=int,
        default=None,
        help="Limit output to top N ranked tags"
    )

    parser.add_argument(
        "--tier",
        choices=["0", "1"],
        default="0",
        help="Output tier: 0=definitions only, 1=definitions+context (default: 0)"
    )

    parser.add_argument(
        "--context-lines",
        type=int,
        default=3,
        help="Number of context lines around each definition (default: 3)"
    )

    parser.add_argument(
        "--mermaid",
        action="store_true",
        help="Output dependency graph as Mermaid flowchart"
    )

    parser.add_argument(
        "--mermaid-top",
        type=int,
        default=30,
        help="Limit mermaid graph to top N nodes (default: 30)"
    )

    parser.add_argument(
        "--exclude-untagged",
        action="store_true",
        help="Skip 'Other files:' section (untagged files) from output"
    )

    parser.add_argument(
        "--exclude-globs",
        nargs="*",
        default=None,
        metavar="PATTERN",
        help="Glob patterns (POSIX, relative to --root) to exclude from auto-scan, "
             "e.g. vendor/** third_party/**. Filters vendored/third-party subtrees "
             "before ranking so first-party code dominates the map."
    )

    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress all output except the map (no verbose, no info messages)"
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Estimate token budget needed without generating the map"
    )

    parser.add_argument(
        "--signature-only",
        action="store_true",
        help="Print a stat-based content signature (16 hex chars) and exit. "
             "No map is built. Used by the lifecycle plugin for cache validation."
    )

    parser.add_argument(
        "--stats-only",
        nargs="?", const=".map",
        metavar="MAP_FILE",
        help="Print token-budget JSON for --root and exit: "
             "{token_estimate, full_repo_estimate, savings_pct} where "
             "token_estimate is the bytes/tokens of MAP_FILE (or the staged "
             "map), full_repo_estimate is all source files under --root, and "
             "savings_pct = context saved vs reading the repo. No map is built. "
             "Used by the lifecycle plugin to enrich cache meta."
    )

    parser.add_argument(
        "--max-files",
        type=int,
        default=0,
        help="Cap on files during auto-discovery when no paths given (default: 0 = no cap)"
    )

    db_group = parser.add_mutually_exclusive_group()
    db_group.add_argument(
        "--db-path",
        metavar="PATH",
        help="Persist per-file tags/refs to this sqlite file (flat-memory tree walk). "
             "Without it, the scan resumes the canonical --init DB when one "
             "exists, else uses in-memory sqlite. --no-db forces in-memory."
    )

    db_group.add_argument(
        "--no-db",
        action="store_true",
        help="Opt OUT of the DB-backed flat-memory tree walk and use the legacy "
             "in-memory nx.MultiDiGraph path. Escape hatch for parity/debugging. "
             "Mutually exclusive with --db-path."
    )

    parser.add_argument(
        "--init",
        action="store_true",
        help="Create/open the canonical DB at <cache>/db/<name>.db "
             "(TRICORDER_CACHE_HOME or <workspace>/.tricorder; never inside "
             "the scanned repo), print its path and exit. Idempotent; "
             "never wipes without --wipe."
    )

    parser.add_argument(
        "--wipe",
        action="store_true",
        help="With --init only: delete the existing canonical DB first. "
             "Stop the MCP server first if it is running against this DB."
    )

    parser.add_argument(
        "--pre-index",
        metavar="SYMBOL",
        help="Enable pre-index probe: ripgrep-first (ctags index fallback), look up SYMBOL, narrow scan to matching files"
    )

    parser.add_argument(
        "--pre-index-max-files",
        type=int,
        default=100,
        help="Max files to include from pre-index probe results (default: 100)"
    )

    parser.add_argument(
        "--pre-index-include-parents",
        type=int,
        default=0,
        help="Also include N parent directories of matched files (default: 0)"
    )

    parser.add_argument(
        "--probe-digest",
        action="store_true",
        help="Print the turn-0 probe digest (language tally + sizes + navigation "
             "hint) for --root and exit. No map build, no token budget -- cheap "
             "even on huge repos. Emits the same text the Hermes/DSH plugins "
             "inject at turn 0."
    )

    parser.add_argument(
        "--db-coverage",
        action="store_true",
        help="Print one-line mapped-DB coverage for --root (mapped: N files, "
             "M tags, db sig X) and exit. Prints nothing when unmapped. "
             "Shared by the Hermes and DSH turn-0 injectors so both stay "
             "byte-identical on mapped repos."
    )

    args = parser.parse_args()

    if args.wipe and not args.init:
        parser.error("--wipe requires --init")

    # Validate an explicit --root before the early-exit flags (--init,
    # --db-coverage, --signature-only, --stats-only, --probe-digest):
    # a root that isn't a directory must fail clean here, not die later
    # in mkdir/compute_signature with a traceback.
    if args.root not in (None, ".", ""):
        _early_root = Path(args.root).resolve()
        if not _early_root.is_dir():
            parser.error(f"--root is not an existing directory: {args.root}")

    # --init: canonical DB path, create dirs, open (schema + journal by size
    # handled in DBStore.__init__), print path, exit. Early, like --probe-digest.
    # The DB lives in the tricorder workspace cache root — never inside the
    # scanned repo.
    if args.init:
        init_root = Path(args.root).resolve()
        init_db = get_cache_root() / "db" / f"{init_root.name}.db"
        init_db.parent.mkdir(parents=True, exist_ok=True)
        if args.wipe and init_db.exists():
            try:
                init_db.unlink()
            except OSError as e:
                # Windows: unlink fails while another process (e.g. the MCP
                # server) holds the DB open. Fail clean, not with a traceback.
                parser.error(
                    f"cannot wipe {init_db}: {e.strerror or e} — the DB may "
                    "be held open by another process (e.g. the MCP server); "
                    "stop it and retry.")
        # Stamp ownership: with an empty meta table, _canonical_db_for's
        # db_root_matches rejects the DB, so --diff/map resumption would
        # never see it until a scan wrote meta. extractor_version=0 marks
        # it "not yet indexed" (staleness unknown), so the first scan does
        # a full rescan and re-stamps with the real signature.
        # Idempotent: only stamp a fresh/empty DB. Re-stamping an indexed
        # DB with extractor_version=0 would mark it "not yet indexed" and
        # force a pointless full rescan of already-mapped files.
        _init_store = None
        try:
            _init_store = DBStore(str(init_db))
            existing_meta = _init_store.get_meta()
            if existing_meta is None:
                _init_store.set_meta(str(init_root), "", 0)
                _init_store.commit()
            elif not db_root_matches(str(init_db), str(init_root)):
                parser.error(
                    f"canonical cache DB {init_db} is already owned by "
                    f"{existing_meta[1]!r}; refusing to overwrite it for "
                    f"{init_root} without --wipe")
        except ValueError as e:
            # Corrupt canonical DB (and no --wipe): message, not traceback.
            parser.error(str(e))
        finally:
            if _init_store is not None:
                _init_store.close()
        print(str(init_db))
        sys.exit(0)

    # --db-coverage: one-line mapped-DB summary for turn-0 injectors (Hermes
    # + DSH). Prints nothing when unmapped. Read-only; never creates or writes
    # (no blind sqlite connect — existence checked first).
    if args.db_coverage:
        _cov_root = Path(args.root).resolve()
        _cov_name = _cov_root.name + ".db"
        # The shared-cache candidate is keyed by directory basename, so a
        # same-named repo elsewhere collides; only a DB whose meta.root is
        # this root may report coverage (otherwise repo B would inherit
        # repo A's "mapped" claim and turn-0 steering would skip a rescan).
        _cov_cands = []
        try:
            _cov_cands.append((get_cache_root() / "db" / _cov_name, False))
        except Exception:
            pass
        for _cand, _cov_local in _cov_cands:
            try:
                if not _cand.exists():
                    continue
                if not _cov_local and not db_root_matches(str(_cand), str(_cov_root)):
                    continue
                _con = read_only_connect(str(_cand))
                try:
                    # Coverage is file_state rows (house rule: never
                    # tags-distinct — tagless files own zero tag rows). A DB
                    # without file_state (pre-Goal-3) has unknowable coverage:
                    # treat as unmapped rather than misreporting tags-distinct.
                    try:
                        _n = _con.execute(
                            "SELECT COUNT(*) FROM file_state").fetchone()[0]
                    except Exception:
                        continue
                    if _n > 0:
                        _t = _con.execute("SELECT COUNT(*) FROM tags").fetchone()[0]
                        _m = _con.execute(
                            "SELECT signature FROM meta ORDER BY rowid DESC LIMIT 1"
                        ).fetchone()
                        _sig = (_m[0][:8] if _m and _m[0] else "?")
                        print(
                            f"mapped: {_n} files, {_t} tags (db sig {_sig}). "
                            "Retrieve, don't rescan: mcp_tricorder_detect to locate, "
                            "mcp_tricorder_symbols for shape, mcp_tricorder_detail for "
                            "body+callers, mcp_tricorder_query to traverse.")
                        break
                finally:
                    _con.close()
            except Exception:
                continue
        sys.exit(0)

    # --signature-only: stat-hash, no map build. Early exit.
    if args.signature_only:
        sig = compute_signature(args.root, args.exclude_globs)
        print(sig)
        sys.exit(0)

    # --stats-only: report budget fields, no map build. Early exit.
    if args.stats_only is not None:
        import json as _json
        token_estimate = 0
        if args.stats_only and args.stats_only != ".":
            try:
                p = Path(args.stats_only)
                if p.exists():
                    token_estimate = count_tokens(p.read_text(encoding="utf-8", errors="replace"), args.model)
            except Exception:
                token_estimate = 0
        budget = repo_budget(args.root, token_estimate, args.model, args.exclude_globs)
        print(_json.dumps(budget))
        sys.exit(0)

    # --probe-digest: turn-0 navigation probe, no map build, no token budget.
    if args.probe_digest:
        probe = probe_project(args.root, args.exclude_globs)
        digest = format_probe_digest(probe, args.root)
        if not digest or probe.get("total_files", 0) == 0:
            # Truly empty/non-code repo -- nothing useful to inject. Exit clean.
            sys.exit(0)
        print(digest)
        sys.exit(0)

    # Set up token counter with specified model
    def token_counter(text: str) -> int:
        return count_tokens(text, args.model)

    # Set up output handlers
    if args.quiet:
        # ponytail: quiet mode -- suppress all logging, only the map matters
        output_handlers = {
            'info': lambda *a: None,
            'warning': lambda *a: None,
            'error': lambda *a: None
        }
    else:
        output_handlers = {
            # JSON mode must stay machine-parseable on stdout: info chatter
            # would corrupt it, so info goes nowhere (warnings/errors
            # already go to stderr and are safe).
            'info': (lambda *a: None) if args.format == "json" else tool_output,
            'warning': tool_warning,
            'error': tool_error
        }

    # Process file arguments
    chat_files_from_args = args.chat_files or [] # These are the paths as strings from the CLI

    # Determine the list of unresolved path specifications that will form the 'other_files'
    # These can be files or directories. find_src_files will expand them.
    unresolved_paths_for_other_files_specs = []
    if args.other_files:  # If --other-files is explicitly provided, it's the source
        unresolved_paths_for_other_files_specs.extend(args.other_files)
    elif args.paths:  # Else, if positional paths are given, they are the source
        unresolved_paths_for_other_files_specs.extend(args.paths)
    # If neither, unresolved_paths_for_other_files_specs remains empty.

    if args.root in (None, '.', ''):
        git_root = find_git_root(unresolved_paths_for_other_files_specs[0] if unresolved_paths_for_other_files_specs else '.')
        if git_root:
            args.root = git_root
        elif unresolved_paths_for_other_files_specs:
            first_spec = unresolved_paths_for_other_files_specs[0]
            if os.path.isdir(first_spec):
                args.root = first_spec

    root_path = Path(args.root).resolve()
    if not root_path.is_dir():
        parser.error(f"--root is not an existing directory: {args.root}")

    def _resolve_files(files):
        """Resolve per-file paths, skipping unresolvable ones (symlink
        loops, dangling links) with a warning instead of crashing."""
        resolved = []
        for f in files:
            r = resolve_or_none(f)
            if r is None:
                output_handlers['warning'](f"Skipping {f}: cannot resolve path")
            else:
                resolved.append(r)
        return resolved

    # Resolve once: explicit --db-path wins, else the canonical --init DB
    # when usable. Map scans write, so an existing-but-unwritable
    # canonical DB (read-only checkout, foreign owner) degrades to
    # in-memory with a warning instead of crashing on the first write.
    # --diff only reads, so it keeps a read-only DB.
    scan_db_path = _effective_db_path(args, root_path, for_write=not args.diff)
    _warn = _unwritable_canonical_warning(args, root_path, scan_db_path)
    if _warn:
        output_handlers['warning'](_warn)

    # --db-path must point at a file, on every path: a directory would die
    # with a raw sqlite3 traceback from DBStore.__init__ (the scan path
    # used to hit this; the --diff guard below only covered diff).
    # A nonexistent path stays legal — a scan creates the DB there.
    if args.db_path and os.path.exists(args.db_path) and not os.path.isfile(args.db_path):
        parser.error(f"--db-path is not a file: {args.db_path}")

    # --diff is read-only: an explicit --db-path must already exist.
    # Letting Tricorder/DBStore connect would create + schema-initialize
    # a fresh file (sqlite3.connect creates 0-byte stubs), silently
    # turning "diff against my index" into "diff against nothing".
    if args.diff and args.db_path and not os.path.isfile(args.db_path):
        parser.error(f"--diff needs an existing index DB; no DB at: {args.db_path}")

    # Pre-index probe runs FIRST, before any full-tree walk: the probe is
    # instant (rg-streamed) and gives the authoritative narrow set. Only if
    # --pre-index is absent OR the probe finds nothing do we walk the tree.
    chat_files = _resolve_files(chat_files_from_args)
    other_files = []
    if args.pre_index:
        output_handlers['info'](f"Probing symbol '{args.pre_index}' in {root_path}...")
        probed_rel_files = probe_and_narrow(
            str(root_path),
            args.pre_index,
            max_files=args.pre_index_max_files,
            include_parents=args.pre_index_include_parents
        )
        if probed_rel_files:
            output_handlers['info'](f"Probe matched {len(probed_rel_files)} files.")
            other_files = _resolve_files([str(root_path / rel) for rel in probed_rel_files])
        else:
            output_handlers['warning'](f"Probe found no matches for '{args.pre_index}', falling back to discovered paths.")

    if not other_files:
        # Resolve relative path specs against root_path, not CWD
        effective_other_files_unresolved = []
        for path_spec_str in unresolved_paths_for_other_files_specs:
            p = Path(path_spec_str)
            if not p.is_absolute():
                p = root_path / path_spec_str
            effective_other_files_unresolved.extend(find_src_files(str(p), exclude_globs=args.exclude_globs))

        # Prefix cap (house rule): --max-files caps the discovery
        # prefix FIRST, then already-mapped files within the prefix are
        # dropped so a resumed rising-cap run doesn't re-parse them.
        # Fixed-cap reruns add zero; resume with a rising cap.
        if args.max_files > 0 and len(effective_other_files_unresolved) > args.max_files:
            output_handlers['warning'](
                f"Explicit paths yielded {len(effective_other_files_unresolved)} files, "
                f"capping to {args.max_files}"
            )
            effective_other_files_unresolved = effective_other_files_unresolved[:args.max_files]
        # Already-mapped files within the prefix are dropped so a resumed
        # rising-cap run doesn't re-parse them — but when the drop empties
        # a non-empty discovery (everything already mapped), fall back to
        # the capped list: the DB-backed dirty diff skips clean files
        # without re-parsing and re-parses dirty ones, so the scan still
        # renders from the index instead of an empty "No files found" map.
        _dropped = drop_mapped_files(
            effective_other_files_unresolved, root_path,
            scan_db_path)
        effective_other_files_unresolved = (
            _dropped if _dropped else effective_other_files_unresolved)
        other_files = _resolve_files(effective_other_files_unresolved)

        # Auto-discover when no explicit/positional paths were provided
        if not other_files:
            if not (args.diff or args.detect is not None or args.symbols is not None):
                output_handlers['info'](f"No explicit files provided, auto-scanning {root_path}...")
            effective_other_files_unresolved = find_src_files(
                str(root_path), exclude_globs=args.exclude_globs)
            # Prefix cap (house rule): --max-files caps the discovery
            # prefix FIRST, then already-mapped files within the prefix are
            # dropped so a resumed rising-cap run doesn't re-parse them.
            # Fixed-cap reruns add zero; resume with a rising cap.
            if args.max_files > 0 and len(effective_other_files_unresolved) > args.max_files:
                output_handlers['warning'](
                    f"Auto-scanned {len(effective_other_files_unresolved)} files, "
                    f"capping to {args.max_files}"
                )
                effective_other_files_unresolved = effective_other_files_unresolved[:args.max_files]
            # Already-mapped files within the prefix are dropped so a resumed
            # rising-cap run doesn't re-parse them — but when the drop empties
            # a non-empty discovery (everything already mapped), fall back to
            # the capped list: the DB-backed dirty diff skips clean files
            # without re-parsing and re-parses dirty ones, so the rescan still
            # renders from the index instead of an empty "No files found" map.
            _dropped = drop_mapped_files(
                effective_other_files_unresolved, root_path,
                scan_db_path)
            effective_other_files_unresolved = (
                _dropped if _dropped else effective_other_files_unresolved)
            other_files = _resolve_files(effective_other_files_unresolved)

    mentioned_fnames = set(args.mentioned_files) if args.mentioned_files else None
    mentioned_idents = set(args.mentioned_idents) if args.mentioned_idents else None

    try:
        repo_map = Tricorder(
            map_tokens=args.map_tokens,
            root=str(root_path),
            token_counter_func=token_counter,
            file_reader_func=read_text,
            output_handler_funcs=output_handlers,
            verbose=args.verbose,
            max_context_window=args.max_context_window,
            exclude_unranked=args.exclude_unranked,
            context_lines=int(args.tier) * args.context_lines,
            exclude_untagged=args.exclude_untagged,
            full_map=args.full,
            use_db=not args.no_db,
            db_path=scan_db_path,
            # --diff is a reader: open the index frozen read-only so a
            # read-only checkout diffs against the baseline instead of
            # crashing on the first write (OperationalError on DDL/commit).
            db_read_only=bool(args.diff and scan_db_path),
        )
    except ValueError as e:
        # Clean failures (corrupt --db-path, etc.): message, not traceback.
        tool_error(str(e))
        sys.exit(1)

    try:
        if args.diff:
            # Delta-map mode: report working-tree changes vs the index and exit.
            diff = repo_map.diff_against_index()
            if args.format == "json":
                import json as _json
                print(_json.dumps(diff, indent=2))
            else:
                if not diff["indexed"]:
                    print("No scan index found — every file is reported as added.")
                for label in ("added", "modified", "deleted"):
                    files = diff[label]
                    print(f"{label.capitalize()} ({len(files)}):")
                    for f in files:
                        # Exact counts survive tag-head capping (tag_counts);
                        # fall back to the head length for old-shaped dicts.
                        ntags = diff["tag_counts"].get(f, len(diff["tags"].get(f, [])))
                        extra = f" [{ntags} tags]" if f in diff["tag_counts"] or f in diff["tags"] else ""
                        print(f"  {f}{extra}")
                if diff["tags_truncated"]:
                    omitted = sum(diff["tags_omitted"].values())
                    print(f"(tag lists capped per file; {omitted} tags omitted, counts exact)")
            return

        if args.detect is not None or args.symbols is not None:
            # Search modes: identifier/symbol lookup without a map build.
            import json as _json
            if args.detect is not None:
                results, _rescue = repo_map.search_identifiers(
                    args.detect, max_results=args.max_results)
                if args.max_tokens:
                    from utils import enforce_search_budget
                    results, truncated, omitted = enforce_search_budget(
                        results, args.max_tokens)
                else:
                    truncated, omitted = False, 0
                if args.format == "json":
                    payload = {"results": results}
                    if truncated:
                        payload.update({"truncated": True,
                                        "total": len(results) + omitted,
                                        "omitted": omitted})
                    print(_json.dumps(payload, indent=2))
                else:
                    if not results:
                        print(f"No matches for '{args.detect}'.")
                    for r in results:
                        q = (f" ({r['quality']})"
                             if r.get("quality") in ("fuzzy", "content") else "")
                        print(f"{r['file']}:{r['line']}  {r['name']}  [{r['kind']}]{q}")
                        for cl in r["context"].splitlines():
                            print(f"    {cl}")
            else:
                results, _rescue = repo_map.search_symbols(
                    args.symbols, limit=args.max_results)
                if args.max_tokens:
                    from utils import enforce_search_budget
                    results, truncated, omitted = enforce_search_budget(
                        results, args.max_tokens)
                else:
                    truncated, omitted = False, 0
                if args.format == "json":
                    payload = {"symbols": results}
                    if truncated:
                        payload.update({"truncated": True,
                                        "total": len(results) + omitted,
                                        "omitted": omitted})
                    print(_json.dumps(payload, indent=2))
                else:
                    if not results:
                        print(f"No matches for '{args.symbols}'.")
                    for s in results:
                        q = f" ({s['quality']})" if s.get("quality") == "fuzzy" else ""
                        print(f"{s['type']:10} {s['name']}  {s['file']}:{s['line']}{q}")
            return

        try:
            ranked_tags, file_report = repo_map.get_ranked_tags(chat_files, other_files)

            if not ranked_tags:
                if not other_files:
                    repo_map.output_handlers['warning'](
                        "No files found. Relative paths are resolved against --root, "
                        "not the current directory. Check that the path exists under your repo root."
                    )
                else:
                    repo_map.output_handlers['warning'](
                        "No tags extracted -- tree-sitter may lack parsers for this language. "
                        "Install missing parsers (e.g. pip install tree-sitter-language-pack)."
                    )

            if args.dry_run:
                if ranked_tags:
                    chat_rel = set(repo_map.get_rel_fname(f) for f in chat_files)
                    sample = ranked_tags[:10]
                    sample_tree = repo_map.to_tree(sample, chat_rel, [])
                    sample_tokens = repo_map.token_count(sample_tree)
                    tokens_per_tag = sample_tokens / len(sample)
                    tags_at_budget = int(args.map_tokens / tokens_per_tag) if tokens_per_tag > 0 else 0
                    full_est = repo_budget(args.root, args.map_tokens, args.model,
                                           args.exclude_globs)["full_repo_estimate"]
                    planned = min(args.map_tokens, full_est)
                    savings = repo_budget(args.root, planned, args.model,
                                          args.exclude_globs)["savings_pct"]
                    repo_map.output_handlers['info'](
                        f"Tags: {len(ranked_tags)} | Tokens per tag: ~{tokens_per_tag:.0f} | "
                        f"Tags at --map-tokens {args.map_tokens}: ~{tags_at_budget} | "
                        f"Full repo estimate: ~{full_est} tokens | "
                        f"Estimated savings: {savings}%"
                    )
                else:
                    repo_map.output_handlers['info']("No tags to estimate.")
                sys.exit(0)

            # ponytail: when --full + --output, stream directly to file
            output_writer = None
            if args.full and args.output:
                output_writer = open(args.output, 'w', encoding='utf-8')

            map_content, file_report = repo_map.get_repo_map(
                chat_files=chat_files,
                other_files=other_files,
                mentioned_fnames=mentioned_fnames,
                mentioned_idents=mentioned_idents,
                force_refresh=args.force_refresh,
                output_writer=output_writer,
            )

            if output_writer is not None:
                # Streaming mode: content is already written to the file
                output_writer.close()
                if not args.quiet:
                    tool_output(f"Map written to {args.output}")
            elif map_content:
                if args.verbose and not args.quiet:
                    tokens = repo_map.token_count(map_content)
                    tool_output(f"Generated map: {len(map_content)} chars, ~{tokens} tokens")

                if args.mermaid:
                    if args.top is not None:
                        ranked_tags = ranked_tags[:args.top]
                    mermaid_output = repo_map.to_mermaid(
                        chat_files, other_files, ranked_tags=ranked_tags,
                        max_nodes=args.mermaid_top
                    )
                    output_text = mermaid_output
                elif args.format == "json":
                    import json
                    if args.top is not None:
                        ranked_tags = ranked_tags[:args.top]
                    json_output = {
                        "tags": [
                            {
                                "name": tag.name,
                                "file": tag.rel_fname,
                                "line": tag.line,
                                "kind": tag.kind,
                                "rank": rank
                            }
                            for rank, tag in ranked_tags
                        ]
                    }
                    map_tokens = repo_map.token_count(map_content)
                    json_output["budget"] = repo_budget(
                        args.root, map_tokens, args.model, args.exclude_globs
                    )
                    output_text = json.dumps(json_output, indent=2)
                else:
                    output_text = map_content

                if args.output:
                    try:
                        safe_write(args.output, output_text, allow_escape=True)
                    except Exception as e:
                        tool_error(f"Failed to write output: {e}")
                        sys.exit(1)
                else:
                    print(output_text)
            else:
                if not args.quiet:
                    tool_warning("No map content generated.")
        except Exception as e:
            repo_map.output_handlers['error'](f"Error generating map: {e}")
            if args.verbose:
                import traceback
                traceback.print_exc()
            sys.exit(1)

    except KeyboardInterrupt:
        # Ctrl+C mid-run (usually mid-scan): leave the DB checkpointed and
        # closed instead of a traceback — a later --diff then sees the
        # partial index rather than a torn WAL. Conventional exit code 130.
        try:
            repo_map.close()
        except Exception:
            pass
        print("Interrupted.", file=sys.stderr)
        sys.exit(130)
    finally:
        # Every exit path (diff/detect/map, success or error) releases the
        # sqlite handle; the scan already checkpointed, so immutable readers
        # see it.
        try:
            repo_map.close()
        except Exception:
            pass


if __name__ == "__main__":
    main()