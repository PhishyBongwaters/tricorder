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
from utils import count_tokens, read_text, Tag, parse_gitignore, discover_src_files, repo_budget, probe_project, format_probe_digest, INJECT_MIN_FILES
from scm import get_scm_fname
from importance import filter_important_files
from core import Tricorder
from ctags_probe import probe_and_narrow


def find_git_root(base: str) -> Optional[str]:
    """Search upward from base for .git/ and return the repo root."""
    p = Path(base).resolve()
    while p != p.parent:
        if (p / '.git').exists():
            return str(p)
        p = p.parent
    return None


def find_src_files(directory: str, exclude_globs: Optional[List[str]] = None) -> List[str]:
    """Find source files in a directory (delegates to shared discover_src_files)."""
    return discover_src_files(directory, use_gitignore=True, exclude_globs=exclude_globs)


def compute_signature(root: str, exclude_globs: Optional[List[str]] = None) -> str:
    """Stat-based signature: path + size + mtime per source file, sha256'd.

    ponytail: stat-based (path+size+mtime), not content hash.
    Misses: content changed but size+mtime unchanged (practically never
    on real filesystems). Upgrade path: content hash if this ever bites.
    """
    h = hashlib.sha256()
    files = sorted(discover_src_files(root, use_gitignore=True,
                                       exclude_globs=exclude_globs))
    for fpath in files:
        try:
            st = os.stat(fpath)
            h.update(f"{fpath}:{st.st_size}:{int(st.st_mtime)}".encode())
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
        default=1000,
        help="Cap on files during auto-discovery when no paths given (default: 1000)"
    )

    parser.add_argument(
        "--pre-index",
        metavar="SYMBOL",
        help="Enable ctags probe: build/use ctags index, look up SYMBOL, narrow scan to matching files"
    )

    parser.add_argument(
        "--pre-index-max-files",
        type=int,
        default=100,
        help="Max files to include from ctags probe results (default: 100)"
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
             "hint) for --root and exit. No map build, no token budget — cheap "
             "even on huge repos. Emits the same text the Hermes/DSH plugins "
             "inject at turn 0."
    )

    args = parser.parse_args()

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
        if not digest or probe.get("total_files", 0) < INJECT_MIN_FILES:
            # Tiny/empty/non-code repo — nothing useful to inject. Exit clean.
            sys.exit(0)
        print(digest)
        sys.exit(0)
    
    # Set up token counter with specified model
    def token_counter(text: str) -> int:
        return count_tokens(text, args.model)
    
    # Set up output handlers
    if args.quiet:
        # ponytail: quiet mode — suppress all logging, only the map matters
        output_handlers = {
            'info': lambda *a: None,
            'warning': lambda *a: None,
            'error': lambda *a: None
        }
    else:
        output_handlers = {
            'info': tool_output,
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

    # Pre-index probe runs FIRST, before any full-tree walk: the probe is
    # instant (rg-streamed) and gives the authoritative narrow set. Only if
    # --pre-index is absent OR the probe finds nothing do we walk the tree.
    chat_files = [str(Path(f).resolve()) for f in chat_files_from_args]
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
            other_files = [str((root_path / rel).resolve()) for rel in probed_rel_files]
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

        if len(effective_other_files_unresolved) > args.max_files:
            output_handlers['warning'](
                f"Explicit paths yielded {len(effective_other_files_unresolved)} files, "
                f"capping to {args.max_files}")
            effective_other_files_unresolved = effective_other_files_unresolved[:args.max_files]
        other_files = [str(Path(f).resolve()) for f in effective_other_files_unresolved]

        # Auto-discover when no explicit/positional paths were provided
        if not other_files:
            output_handlers['info'](f"No explicit files provided, auto-scanning {root_path}...")
            effective_other_files_unresolved = find_src_files(
                str(root_path), exclude_globs=args.exclude_globs)
            if len(effective_other_files_unresolved) > args.max_files:
                output_handlers['warning'](
                    f"Auto-scanned {len(effective_other_files_unresolved)} files, "
                    f"capping to {args.max_files}")
                effective_other_files_unresolved = effective_other_files_unresolved[:args.max_files]
            other_files = [str(Path(f).resolve()) for f in effective_other_files_unresolved]
    
    mentioned_fnames = set(args.mentioned_files) if args.mentioned_files else None
    mentioned_idents = set(args.mentioned_idents) if args.mentioned_idents else None
    
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
        exclude_untagged=args.exclude_untagged
    )
    
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
                    "No tags extracted — tree-sitter may lack parsers for this language. "
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

        map_content, _ = repo_map.get_repo_map(
            chat_files=chat_files,
            other_files=other_files,
            mentioned_fnames=mentioned_fnames,
            mentioned_idents=mentioned_idents,
            force_refresh=args.force_refresh
        )

        if map_content:
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
                Path(args.output).write_text(output_text, encoding="utf-8")
            else:
                print(output_text)
        else:
            if not args.quiet:
                tool_output("No repository map generated.")
            
    except KeyboardInterrupt:
        tool_error("Interrupted by user")
        sys.exit(1)
    except Exception as e:
        tool_error(f"Error generating repository map: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()