#!/usr/bin/env python3
"""
Standalone RepoMap Tool

A command-line tool that generates a "map" of a software repository,
highlighting important files and definitions based on their relevance.
Uses Tree-sitter for parsing and PageRank for ranking importance.
"""

import argparse
import os
import sys
from pathlib import Path
from typing import List, Optional

from utils import count_tokens, read_text, Tag, parse_gitignore
from scm import get_scm_fname
from importance import filter_important_files
from repomap_class import RepoMap


def find_git_root(base: str) -> Optional[str]:
    """Search upward from base for .git/ and return the repo root."""
    p = Path(base).resolve()
    while p != p.parent:
        if (p / '.git').exists():
            return str(p)
        p = p.parent
    return None


def find_src_files(directory: str) -> List[str]:
    """Find source files in a directory."""
    if not os.path.isdir(directory):
        return [directory] if os.path.isfile(directory) else []
    
    # ponytail: skip noise extensions that can't have tree-sitter symbols
    _SKIP_EXTS = {'.frag', '.vert', '.inc', '.icns', '.plist', '.entitlements',
                  '.cmake.in', '.h.in', '.cpp.in', '.hpp.in'}
    # ponytail: Windows device files that tree-sitter can't parse
    _SKIP_NAMES = {'nul', 'con', 'prn', 'aux', 'com1', 'com2', 'com3', 'com4',
                   'lpt1', 'lpt2', 'lpt3', 'lpt4', 'lpt5', 'lpt6', 'lpt7', 'lpt8', 'lpt9'}
    # ponytail: parse .gitignore for dirs to skip — covers build/, dist/, etc.
    git_root = find_git_root(directory) or directory
    gitignore_dirs = parse_gitignore(git_root)
    # ponytail: always-skip dirs (hardcoded fallback when no .gitignore)
    builtin_skip = {'node_modules', '__pycache__', 'venv', 'env', 'build', 'dist', '.tox', '.eggs'}
    skip_dirs = gitignore_dirs | builtin_skip
    
    src_files = []
    for root, dirs, files in os.walk(directory):
        # Skip hidden directories and common non-source directories
        dirs[:] = [d for d in dirs if not d.startswith('.') and d not in skip_dirs]
        
        for file in files:
            if file.startswith('.') or file.lower() in _SKIP_NAMES:
                continue
            p = Path(file)
            if p.suffix in _SKIP_EXTS or file.endswith(('.cmake.in', '.h.in', '.cpp.in', '.hpp.in')):
                continue
            full_path = os.path.join(root, file)
            src_files.append(full_path)
    
    return src_files


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
        "--quiet",
        action="store_true",
        help="Suppress all output except the map (no verbose, no info messages)"
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Estimate token budget needed without generating the map"
    )
    
    args = parser.parse_args()
    
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
    
    # ponytail: auto-detect git repo root FIRST, so relative path specs
    # can be resolved against --root before find_src_files tries to walk them.
    # Previously find_src_files ran on raw relative paths (resolved against CWD,
    # not the repo root), which made `repomap.py src/ --root /other/repo` silently
    # find 0 files and emit a misleading "No tags extracted" parser-missing warning.
    if args.root in (None, '.', ''):
        git_root = find_git_root(unresolved_paths_for_other_files_specs[0] if unresolved_paths_for_other_files_specs else '.')
        if git_root:
            args.root = git_root
        elif unresolved_paths_for_other_files_specs:
            first_spec = unresolved_paths_for_other_files_specs[0]
            if os.path.isdir(first_spec):
                args.root = first_spec

    root_path = Path(args.root).resolve()

    # Resolve relative path specs against root_path, not CWD
    effective_other_files_unresolved = []
    for path_spec_str in unresolved_paths_for_other_files_specs:
        p = Path(path_spec_str)
        if not p.is_absolute():
            p = root_path / path_spec_str
        effective_other_files_unresolved.extend(find_src_files(str(p)))
    
    # chat_files for RepoMap are from --chat-files argument, resolved.
    chat_files = [str(Path(f).resolve()) for f in chat_files_from_args]
    # other_files for RepoMap are the effective_other_files, resolved after expansion.
    other_files = [str(Path(f).resolve()) for f in effective_other_files_unresolved]

    # chat files resolved above
    
    # Convert mentioned files to sets
    mentioned_fnames = set(args.mentioned_files) if args.mentioned_files else None
    mentioned_idents = set(args.mentioned_idents) if args.mentioned_idents else None
    
    # Create RepoMap instance
    repo_map = RepoMap(
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
    
    # Generate the map
    try:
        # Pre-compute ranked tags for mermaid/json branches
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
            # Estimate tokens per tag by rendering top 10 tags
            if ranked_tags:
                chat_rel = set(repo_map.get_rel_fname(f) for f in chat_files)
                sample = ranked_tags[:10]
                # Exclude untagged files from estimate to measure tag cost only
                sample_tree = repo_map.to_tree(sample, chat_rel, [])
                sample_tokens = repo_map.token_count(sample_tree)
                tokens_per_tag = sample_tokens / len(sample)
                tags_at_budget = int(args.map_tokens / tokens_per_tag) if tokens_per_tag > 0 else 0
                repo_map.output_handlers['info'](
                    f"Tags: {len(ranked_tags)} | Tokens per tag: ~{tokens_per_tag:.0f} | "
                    f"Tags at --map-tokens {args.map_tokens}: ~{tags_at_budget} | "
                    f"Full repo estimate: ~{int(tokens_per_tag * len(ranked_tags))} tokens"
                )
            else:
                repo_map.output_handlers['info']("No tags to estimate.")
            sys.exit(0)

        # Generate the map
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
                # Mermaid output: dependency graph
                if args.top is not None:
                    ranked_tags = ranked_tags[:args.top]
                mermaid_output = repo_map.to_mermaid(
                    chat_files, other_files, ranked_tags=ranked_tags,
                    max_nodes=args.mermaid_top
                )
                output_text = mermaid_output
            elif args.format == "json":
                # JSON output: tags, ranks, and file metadata
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
