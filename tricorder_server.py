import asyncio
import json
import os
import logging
import sys
from pathlib import Path
from typing import List, Optional, Dict, Any, Set
import dataclasses

from fastmcp import FastMCP, settings
from core import Tricorder
from utils import count_tokens, read_text, parse_gitignore, discover_src_files, SymbolRecord, repo_budget, parse_query_dsl, ParsedQuery
from scm import get_scm_fname
from importance import filter_important_files

# Thin wrapper kept for backward compat (tests import this name).
def find_src_files(directory: str, exclude_globs: Optional[List[str]] = None) -> List[str]:
    return discover_src_files(directory, use_gitignore=True, exclude_globs=exclude_globs)

# Configure logging - only show errors
root_logger = logging.getLogger()
root_logger.setLevel(logging.ERROR)

# Create console handler for errors only
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.ERROR)
console_formatter = logging.Formatter('%(levelname)-5s %(asctime)-15s %(name)s:%(funcName)s:%(lineno)d - %(message)s')
console_handler.setFormatter(console_formatter)
root_logger.addHandler(console_handler)

# Suppress FastMCP logs
fastmcp_logger = logging.getLogger('fastmcp')
fastmcp_logger.setLevel(logging.ERROR)
# Suppress server startup message
server_logger = logging.getLogger('fastmcp.server')
server_logger.setLevel(logging.ERROR)

log = logging.getLogger(__name__)

# Set global stateless_http setting
settings.stateless_http = True

# Create MCP server
mcp = FastMCP("tricorder")

# ponytail: advisory tier tracker — survives across calls within a server process.
# Can't enforce agent behavior (MCP is stateless per call) but can warn in the response.
_tier_history: Dict[str, dict] = {}  # {project_root: {"last_tier": int, "last_format": str, "map_file": str}}


def _savings_pct(token_estimate: int, full_repo_estimate: int) -> float:
    """% of full-repo context saved by a token estimate. 0 when repo is empty or
    the estimate exceeds the repo (a tier-1 map can cost more than reading it)."""
    if not full_repo_estimate:
        return 0.0
    return round(max(0.0, 1 - token_estimate / full_repo_estimate) * 100, 1)


def _full_repo_tokens(project_root: str) -> int:
    """Estimate full-repo token cost (sum of raw source-file reads)."""
    return repo_budget(project_root, 0)["full_repo_estimate"]


def _budget_fields(resp: dict, full_repo_tokens: int) -> dict:
    """Add token_estimate/full_repo_estimate/savings_pct to a search-tool response.

    token_estimate = tokens of the serialized (non-error) response body.
    savings_pct = context saved vs reading the full repo. 0 when repo is empty.
    """
    tok = count_tokens(json.dumps(resp), "gpt-4")
    return {
        "token_estimate": tok,
        "full_repo_estimate": full_repo_tokens,
        "savings_pct": _savings_pct(tok, full_repo_tokens),
    }


@mcp.tool()
async def tricorder_scan(
    project_root: str,
    chat_files: Optional[List[str]] = None,
    other_files: Optional[List[str]] = None,
    token_limit: Any = 8192,  # Accept any type to handle empty strings
    exclude_unranked: bool = False,
    force_refresh: bool = False,
    mentioned_files: Optional[List[str]] = None,
    mentioned_idents: Optional[List[str]] = None,
    verbose: bool = False,
    max_context_window: Optional[int] = None,
    tier: int = 0,
    context_lines: int = 3,
    output_format: str = "text",
    max_files: int = 1000,
    output_file: Optional[str] = None,
    dry_run: bool = False,
    exclude_globs: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Generate a repository map for the specified files, providing a list of function prototypes and variables for files as well as relevant related
    files. Provide filenames relative to the project_root. In addition to the files provided, relevant related files will also be included with a
    very small ranking boost.

    :param project_root: Root directory of the project to search.  (must be an absolute path!)
    :param chat_files: A list of file paths that are currently in the chat context. These files will receive the highest ranking.
    :param other_files: A list of other relevant file paths in the repository to consider for the map. They receive a lower ranking boost than mentioned_files and chat_files.
    :param token_limit: The maximum number of tokens the generated repository map should occupy. Defaults to 8192.
    :param exclude_unranked: If True, files with a PageRank of 0.0 will be excluded from the map. Defaults to False.
    :param force_refresh: If True, forces a refresh of the repository map cache. Defaults to False.
    :param mentioned_files: Optional list of file paths explicitly mentioned in the conversation and receive a mid-level ranking boost.
    :param mentioned_idents: Optional list of identifiers explicitly mentioned in the conversation, to boost their ranking.
    :param verbose: If True, enables verbose logging for the Tricorder generation process. Defaults to False.
    :param max_context_window: Optional maximum context window size for token calculation, used to adjust map token limit when no chat files are provided.
    :param max_files: Maximum number of files to auto-scan when other_files is not provided. Prevents full-scan bloat on large repos. Defaults to 1000.
    :param output_file: If provided, write the map to this file path instead of returning it in the response. The response will contain only the file path and a token estimate — use this to avoid flooding the agent's context with large maps. Recommended for repos > 50 files.
    :param output_format: Output format — "text" (default) for prioritized definitions, "mermaid" for dependency graph as Mermaid flowchart.
    :param tier: 0 for definitions only (T0, cheapest), 1 for definitions + context lines (T1, expensive). Stop at the lowest tier that answers the question.
    :param context_lines: Lines of context around each definition when tier=1.
    :param dry_run: If True, estimate token budget without generating the map. Returns tag count, tokens per tag, tags at budget, and full repo estimate.
    :param exclude_globs: Optional list of glob patterns (POSIX, relative to project_root) to exclude from auto-scan, e.g. ["vendor/**", "third_party/**"]. Filters vendored/third-party subtrees before ranking so first-party code dominates the map. Ignored when other_files is explicitly provided.
    :returns: A dictionary containing:
        - If dry_run: 'tags', 'tokens_per_tag', 'tags_at_budget', 'full_repo_estimate'.
        - If output_file is set: 'map_file' (path), 'token_estimate' (int), 'tier' (int), 'format' (str), 'report' (dict), and optionally 'tier_hint' (advisory).
        - If output_file is None: 'map' (the full map string), 'report' (dict) — backward compatible.
        Or an 'error' key if an error occurred.
    """
    if not os.path.isdir(project_root):
        return {"error": f"Project root directory not found: {project_root}"}

    # 1. Handle and validate parameters
    # Convert token_limit to integer with fallback
    try:
        token_limit = int(token_limit) if token_limit else 8192
    except (TypeError, ValueError):
        token_limit = 8192
    
    # Ensure token_limit is positive
    if token_limit <= 0:
        token_limit = 8192
    
    chat_files_list = chat_files or []
    mentioned_fnames_set = set(mentioned_files) if mentioned_files else None
    mentioned_idents_set = set(mentioned_idents) if mentioned_idents else None

    # 2. If a specific list of other_files isn't provided, scan the whole root directory.
    # This should happen regardless of whether chat_files are present.
    effective_other_files = []
    if other_files:
        effective_other_files = other_files
    else:
        log.info("No other_files provided, scanning root directory for context...")
        effective_other_files = find_src_files(project_root, exclude_globs=exclude_globs)
        if len(effective_other_files) > max_files:
            log.warning(f"Auto-scanned {len(effective_other_files)} files, capping to {max_files}")
            effective_other_files = effective_other_files[:max_files]

    # Add a print statement for debugging so you can see what the tool is working with.
    log.debug(f"Chat files: {chat_files_list}")
    log.debug(f"Effective other_files count: {len(effective_other_files)}")

    # If after all that we have no files, we can exit early.
    if not chat_files_list and not effective_other_files:
        log.info("No files to process.")
        return {"map": "No files found to generate a map."}

    # 3. Resolve paths relative to project root
    root_path = Path(project_root).resolve()
    abs_chat_files = [str(Path(str(root_path / f)).resolve()) for f in chat_files_list]
    abs_other_files = [str(Path(str(root_path / f)).resolve()) for f in effective_other_files]
    
    # Remove any chat files from the other_files list to avoid duplication
    abs_chat_files_set = set(abs_chat_files)
    abs_other_files = [f for f in abs_other_files if f not in abs_chat_files_set]

    # 4. Instantiate and run Tricorder
    try:
        repo_mapper = Tricorder(
            map_tokens=token_limit,
            root=str(root_path),
            token_counter_func=lambda text: count_tokens(text, "gpt-4"),
            file_reader_func=read_text,
            output_handler_funcs={'info': log.info, 'warning': log.warning, 'error': log.error},
            verbose=verbose,
            exclude_unranked=exclude_unranked,
            max_context_window=max_context_window,
            context_lines=context_lines if tier > 0 else 0,
            exclude_globs=exclude_globs
        )
    except Exception as e:
        log.exception(f"Failed to initialize Tricorder for project '{project_root}': {e}")
        return {"error": f"Failed to initialize Tricorder: {str(e)}"}

    # 5. Dry run / output_file — estimate + map to disk
    # ponytail: when output_file is set, the map goes to disk anyway — no need to
    # render it into context. Just return the estimate + metadata.
    # Agent can pass dry_run=True explicitly, or rely on output_file triggering it.
    try:
        if dry_run or output_file:
            ranked_tags, file_report = await asyncio.to_thread(
                repo_mapper.get_ranked_tags,
                chat_fnames=abs_chat_files,
                other_fnames=abs_other_files
            )
            if not ranked_tags:
                return {"error": "No tags extracted — tree-sitter may lack parsers for this language."}
            chat_rel = set(repo_mapper.get_rel_fname(f) for f in abs_chat_files)
            sample = ranked_tags[:10]
            sample_tree = repo_mapper.to_tree(sample, chat_rel, [])
            sample_tokens = repo_mapper.token_count(sample_tree)
            tokens_per_tag = sample_tokens / len(sample)
            tags_at_budget = int(token_limit / tokens_per_tag) if tokens_per_tag > 0 else 0

            if dry_run:
                full_repo_estimate = _full_repo_tokens(project_root)
                # Map is clamped to min(token_limit, full_repo) — honest best-case savings
                map_tokens_planned = min(token_limit, full_repo_estimate)
                result = {
                    "tags": len(ranked_tags),
                    "tokens_per_tag": round(tokens_per_tag, 0),
                    "tags_at_budget": tags_at_budget,
                    "full_repo_estimate": full_repo_estimate,
                    "token_estimate": map_tokens_planned,
                    "savings_pct": _savings_pct(map_tokens_planned, full_repo_estimate),
                    "definition_matches": file_report.definition_matches,
                    "reference_matches": file_report.reference_matches,
                    "total_files_considered": file_report.total_files_considered,
                }
                # Advisory tier hint: T0 incomplete (truncated at budget)
                if tags_at_budget < len(ranked_tags):
                    pct = round(tags_at_budget / len(ranked_tags) * 100, 1)
                    result["tier_hint"] = f"T0 incomplete: {tags_at_budget}/{len(ranked_tags)} tags fit ({pct}%). Consider tier=1 or higher token_limit."
                return result

            # output_file path — generate the actual map, write to disk, return metadata
            if output_format == "mermaid":
                map_content = await asyncio.to_thread(
                    repo_mapper.to_mermaid,
                    chat_fnames=abs_chat_files,
                    other_fnames=abs_other_files,
                    mentioned_fnames=mentioned_fnames_set,
                    mentioned_idents=mentioned_idents_set
                )
                report_dict = {"excluded": {}, "definition_matches": 0, "reference_matches": 0, "total_files_considered": 0}
            else:
                map_content, file_report = await asyncio.to_thread(
                    repo_mapper.get_repo_map,
                    chat_files=abs_chat_files,
                    other_files=abs_other_files,
                    mentioned_fnames=mentioned_fnames_set,
                    mentioned_idents=mentioned_idents_set,
                    force_refresh=force_refresh
                )
                map_tokens_actual = count_tokens(map_content or "", "gpt-4")
                remaining_tokens = max(0, token_limit - map_tokens_actual)
                remaining_chars = remaining_tokens * 4
                excluded_list = list(file_report.excluded.items())
                capped_excluded = {}
                for path, reason in excluded_list:
                    entry_size = len(path) + len(reason) + 20
                    if len(capped_excluded) * 20 + entry_size > remaining_chars:
                        break
                    capped_excluded[path] = reason
                report_dict = {
                    "excluded": capped_excluded,
                    "excluded_total": len(file_report.excluded),
                    "definition_matches": file_report.definition_matches,
                    "reference_matches": file_report.reference_matches,
                    "total_files_considered": file_report.total_files_considered
                }

            token_estimate = count_tokens(map_content or "", "gpt-4")
            full_repo_estimate = _full_repo_tokens(project_root)

            out_path = Path(output_file)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(map_content, encoding="utf-8")
            result: Dict[str, Any] = {
                "map_file": str(out_path),
                "token_estimate": token_estimate,
                "full_repo_estimate": full_repo_estimate,
                "savings_pct": _savings_pct(token_estimate, full_repo_estimate),
                "tags": len(ranked_tags),
                "tokens_per_tag": round(tokens_per_tag, 0),
                "tags_at_budget": tags_at_budget,
                "full_repo_estimate": int(tokens_per_tag * len(ranked_tags)),
                "tier": tier,
                "format": output_format,
                "report": report_dict,
            }
            # Advisory tier hint: T0 incomplete (truncated at budget)
            if tags_at_budget < len(ranked_tags):
                pct = round(tags_at_budget / len(ranked_tags) * 100, 1)
                result["tier_hint"] = f"T0 incomplete: {tags_at_budget}/{len(ranked_tags)} tags fit ({pct}%). Consider tier=1 or higher token_limit."
            # Advisory tier hint: upgrade from previous tier
            prev = _tier_history.get(project_root)
            if prev:
                if tier > prev["last_tier"] and prev.get("map_file"):
                    result["tier_hint"] = (
                        f"Upgrading from T{prev['last_tier']} to T{tier}. "
                        f"The T{prev['last_tier']} map at {prev['map_file']} may have been sufficient — "
                        f"only escalate tiers if the previous tier genuinely failed to answer your question."
                    )
            _tier_history[project_root] = {"last_tier": tier, "last_format": output_format, "map_file": str(out_path)}
            return result

        # Stdout path (backward compat — no output_file, no dry_run)
        if output_format == "mermaid":
            map_content = await asyncio.to_thread(
                repo_mapper.to_mermaid,
                chat_fnames=abs_chat_files,
                other_fnames=abs_other_files,
                mentioned_fnames=mentioned_fnames_set,
                mentioned_idents=mentioned_idents_set
            )
            report_dict = {"excluded": {}, "definition_matches": 0, "reference_matches": 0, "total_files_considered": 0}
        else:
            map_content, file_report = await asyncio.to_thread(
                repo_mapper.get_repo_map,
                chat_files=abs_chat_files,
                other_files=abs_other_files,
                mentioned_fnames=mentioned_fnames_set,
                mentioned_idents=mentioned_idents_set,
                force_refresh=force_refresh
            )
            map_tokens_actual = count_tokens(map_content or "", "gpt-4")
            remaining_tokens = max(0, token_limit - map_tokens_actual)
            remaining_chars = remaining_tokens * 4
            excluded_list = list(file_report.excluded.items())
            capped_excluded = {}
            for path, reason in excluded_list:
                entry_size = len(path) + len(reason) + 20
                if len(capped_excluded) * 20 + entry_size > remaining_chars:
                    break
                capped_excluded[path] = reason
            report_dict = {
                "excluded": capped_excluded,
                "excluded_total": len(file_report.excluded),
                "definition_matches": file_report.definition_matches,
                "reference_matches": file_report.reference_matches,
                "total_files_considered": file_report.total_files_considered
            }
        _tok = count_tokens(map_content or "", "gpt-4")
        _full = _full_repo_tokens(project_root)
        return {"map": map_content, "report": report_dict,
                "token_estimate": _tok,
                "full_repo_estimate": _full,
                "savings_pct": _savings_pct(_tok, _full)}

    except Exception as e:
        log.exception(f"Error generating repository map for project '{project_root}': {e}")
        return {"error": f"Error generating repository map: {str(e)}"}
    
@mcp.tool()
async def tricorder_detect(
    project_root: str,
    query: str,
    max_results: int = 50,
    context_lines: int = 2,
    include_definitions: bool = True,
    include_references: bool = True
) -> Dict[str, Any]:
    """Search for identifiers in code files. Get back a list of matching identifiers with their file, line number, and context.
       When searching, just use the identifier name without any special characters, prefixes or suffixes. The search is 
       case-insensitive.

    Args:
        project_root: Root directory of the project to search.  (must be an absolute path!)
        query: Search query (identifier name)
        max_results: Maximum number of results to return
        context_lines: Number of lines of context to show
        include_definitions: Whether to include definition occurrences
        include_references: Whether to include reference occurrences
    
    Returns:
        Dictionary containing search results or error message
    """
    if not os.path.isdir(project_root):
        return {"error": f"Project root directory not found: {project_root}"}

    project_root = str(Path(project_root).resolve())

    try:
        # Initialize Tricorder with search-specific settings
        repo_map = Tricorder(
            root=project_root,
            token_counter_func=lambda text: count_tokens(text, "gpt-4"),
            file_reader_func=read_text,
            output_handler_funcs={'info': log.info, 'warning': log.warning, 'error': log.error},
            verbose=False,
            exclude_unranked=True
        )

        # Find all source files in the project
        all_files = find_src_files(project_root)
        
        # Get all tags (definitions and references) for all files
        all_tags = []
        for file_path in all_files:
            rel_path = str(Path(file_path).relative_to(project_root))
            tags = repo_map.get_tags(file_path, rel_path)
            all_tags.extend(tags)

        # Filter tags based on search query and options
        matching_tags = []
        query_lower = query.lower()
        
        for tag in all_tags:
            if query_lower in tag.name.lower():
                if (tag.kind == "def" and include_definitions) or \
                   (tag.kind == "ref" and include_references):
                    matching_tags.append(tag)

        # Sort by relevance (definitions first, then references)
        matching_tags.sort(key=lambda x: (x.kind != "def", x.name.lower().find(query_lower)))

        # Limit results
        matching_tags = matching_tags[:max_results]

        # Format results with context
        results = []
        for tag in matching_tags:
            file_path = str(Path(project_root) / tag.rel_fname)
            
            # Calculate context range based on context_lines parameter
            start_line = max(1, tag.line - context_lines)
            end_line = tag.line + context_lines
            context_range = list(range(start_line, end_line + 1))
            
            context = repo_map.render_tree(
                file_path,
                tag.rel_fname,
                context_range
            )
            
            if context:
                results.append({
                    "file": tag.rel_fname,
                    "line": tag.line,
                    "name": tag.name,
                    "kind": tag.kind,
                    "context": context
                })

        resp = {"results": results}
        resp.update(_budget_fields(resp, _full_repo_tokens(project_root)))
        return resp

    except Exception as e:
        log.exception(f"Error searching identifiers in project '{project_root}': {e}")
        return {"error": f"Error searching identifiers: {str(e)}"}    

@mcp.tool()
async def tricorder_symbols(
    project_root: str,
    query: str = "",
    type: Optional[str] = None,
    file: Optional[str] = None,
    limit: int = 50,
) -> Dict[str, Any]:
    """Search for code symbols by name, type, or file path. Returns matching symbols with their name, type, file, line range, signature, docstring, language, and tree-sitter kind.

    Args:
        project_root: Root directory of the project to search. (must be an absolute path!)
        query: Substring match on symbol name (case-insensitive). Empty string matches all.
        type: Filter by symbol type — function, class, type, variable, method, or import. Exact match.
        file: Filter by file path — path contains the given string.
        limit: Maximum results to return. Defaults to 50, caps at 200.

    Returns:
        Dictionary containing 'symbols' (list of symbol records) or 'error' key.
    """
    if not os.path.isdir(project_root):
        return {"error": f"Project root directory not found: {project_root}"}

    project_root = str(Path(project_root).resolve())

    # Enforce limit cap
    limit = min(max(limit, 1), 200)

    try:
        repo_map = Tricorder(
            root=project_root,
            token_counter_func=lambda text: count_tokens(text, "gpt-4"),
            file_reader_func=read_text,
            output_handler_funcs={'info': log.info, 'warning': log.warning, 'error': log.error},
            verbose=False,
        )

        all_files = find_src_files(project_root)
        all_symbols = []

        for file_path in all_files:
            rel_path = str(Path(file_path).relative_to(project_root))

            # File filter - match against relative path (POSIX normalized)
            if file and file.lower() not in rel_path.replace('\\', '/').lower():
                continue

            symbols = repo_map.get_symbols(file_path, rel_path)
            all_symbols.extend(symbols)

        # Apply filters
        results = []
        query_lower = query.lower()

        for sym in all_symbols:
            # Name filter (substring, case-insensitive)
            if query and query_lower not in sym.name.lower():
                continue

            # Type filter (exact match)
            if type and sym.type != type:
                continue

            results.append(sym.to_dict())

        # Sort: definitions first, then by name
        results.sort(key=lambda x: (x["type"], x["name"].lower()))

        # Apply limit
        results = results[:limit]

        resp = {"symbols": results, "total": len(results), "limit": limit}
        resp.update(_budget_fields(resp, _full_repo_tokens(project_root)))
        return resp

    except Exception as e:
        log.exception(f"Error searching symbols in project '{project_root}': {e}")
        return {"error": f"Error searching symbols: {str(e)}"}

@mcp.tool()
async def tricorder_detail(
    project_root: str,
    file: str,
    name: str,
    line: int = 0,
) -> Dict[str, Any]:
    """Get full details for a specific code symbol by file path, name, and optional line number.

    Returns the symbol record with additional fields:
      - body: the actual code body (first 500 chars)
      - callers: list of {file, line, cross_file} dicts — references to this symbol
      - callees: list of {name, file, line, cross_file} dicts — symbols this symbol calls
    Callers/callees are populated from tree-sitter reference captures:
      - In-file: references within the same file
      - Cross-file: full-repo scan matching references to definitions
    cross_file=True means the reference/definition is in a different file.

    If the symbol is not found, returns {"error": "not found"} with exit code 0.

    Args:
        project_root: Root directory of the project. (must be an absolute path!)
        file: File path containing the symbol (relative to project_root or absolute).
        name: Symbol name to look up.
        line: Optional line number to disambiguate symbols with the same name.

    Returns:
        Dictionary containing 'symbol' (symbol record dict) or 'error' key.
    """
    if not os.path.isdir(project_root):
        return {"error": f"Project root directory not found: {project_root}"}

    project_root = str(Path(project_root).resolve())

    # Resolve file path — accept relative or absolute
    file_path = Path(file)
    if not file_path.is_absolute():
        file_path = Path(project_root) / file_path
    file_path = str(file_path.resolve())

    if not os.path.isfile(file_path):
        return {"error": "not found"}

    try:
        repo_map = Tricorder(
            root=project_root,
            token_counter_func=lambda text: count_tokens(text, "gpt-4"),
            file_reader_func=read_text,
            output_handler_funcs={'info': log.info, 'warning': log.warning, 'error': log.error},
            verbose=False,
        )

        detail = repo_map.get_symbol_detail(file_path, name, line)
        if detail is None:
            return {"error": "not found"}

        resp = {"symbol": detail.to_dict()}
        resp.update(_budget_fields(resp, _full_repo_tokens(project_root)))
        return resp

    except Exception as e:
        log.exception(f"Error getting symbol details for '{name}' in '{file_path}': {e}")
        return {"error": f"Error getting symbol details: {str(e)}"}


@mcp.tool()
async def tricorder_query(
    project_root: str,
    query: str,
    token_limit: int = 2048,
) -> Dict[str, Any]:
    """Execute a graph traversal query on the codebase.

    DSL Grammar:
        query := traversal ('|' traversal)*
        traversal := kind '(' target ')' modifiers?
        kind := "callers" | "callees" | "refs" | "defs"
        target := quoted string (single or double quotes)
        modifiers := (modifier)*
        modifier := "depth=" INT | "exclude=" GLOB | "include=" GLOB
                  | "type=" ("function"|"class"|"method"|"variable") | "limit=" INT

    Examples:
        "callers('authenticate') depth=2"              # all callers up to 2 hops
        "callees('main') depth=1 exclude=tests/**"     # direct callees, skip tests
        "refs('Config') type=class limit=50"           # all references to class Config
        "callers('foo') | callees('bar') depth=3"      # chained traversals

    Args:
        project_root: Root directory of the project (must be absolute path!)
        query: Graph query DSL string
        token_limit: Maximum tokens for response (default 2048)

    Returns:
        Dictionary with:
        - nodes: list of {name, file, line, type}
        - edges: list of {from, to, from_file, to_file, from_line, to_line, type}
        - token_estimate, full_repo_estimate, savings_pct
        - tier_hint (if response truncated)
        - stats: {nodes_visited, edges_traversed}
    """
    if not os.path.isdir(project_root):
        return {"error": f"Project root directory not found: {project_root}"}

    project_root = str(Path(project_root).resolve())

    # Parse query DSL
    try:
        parsed = parse_query_dsl(query)
    except ValueError as e:
        return {"error": f"Invalid query syntax: {e}"}

    if not parsed.steps:
        return {"error": "Empty query"}

    try:
        repo_map = Tricorder(
            root=project_root,
            token_counter_func=lambda text: count_tokens(text, "gpt-4"),
            file_reader_func=read_text,
            output_handler_funcs={'info': log.info, 'warning': log.warning, 'error': log.error},
            verbose=False,
        )

        result = repo_map.query_graph(parsed, token_limit=token_limit)
        return result

    except Exception as e:
        log.exception(f"Error executing graph query '{query}' on project '{project_root}': {e}")
        return {"error": f"Error executing graph query: {str(e)}"}

# --- Main Entry Point ---
def main():
    # Run the MCP server
    log.debug("Starting FastMCP server...")
    mcp.run()

if __name__ == "__main__":
    main()
