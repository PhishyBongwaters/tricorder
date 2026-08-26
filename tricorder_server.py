import asyncio
import json
import os
import logging
import sys
from collections import OrderedDict
from functools import lru_cache
from pathlib import Path
from typing import List, Optional, Dict, Any, Set
import dataclasses

# Pin this project's dir ahead of sys.path so `from utils import ...` / `from core import ...`
# resolve to THIS repo, not a same-named module in another venv/install (the Hermes agent
# shadowed D:/Projects/tricorder/utils.py with its own utils.py, killing the MCP server at import).
sys.path.insert(0, str(Path(__file__).resolve().parent))

from fastmcp import FastMCP, settings
from core import Tricorder
from utils import count_tokens, read_text, parse_gitignore, discover_src_files, SymbolRecord, repo_budget, parse_query_dsl, ParsedQuery
from scm import get_scm_fname
from importance import filter_important_files
from ctags_probe import probe_and_narrow

# Thin wrapper kept for backward compat (tests import this name).
def find_src_files(directory: str, exclude_globs: Optional[List[str]] = None) -> List[str]:
    # TC-002: surface the resource-envelope partial-scan report on the module
    # so callers (tricorder_scan auto-discovery) can warn the agent.
    return discover_src_files(directory, use_gitignore=True, exclude_globs=exclude_globs,
                              report=_last_scan_report)


# TC-002: populated by find_src_files() so the scan envelope warning can be
# attached to the response when the walk hit a resource budget.
_last_scan_report: dict = {}

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
# Bounded LRU (OrderedDict) prevents unbounded growth across many project roots.
_MAX_TIER_HISTORY = 128

_tier_history_store: "OrderedDict[str, dict]" = OrderedDict()


def _tier_history_get(project_root: str) -> Optional[dict]:
    """Get tier history for a project root (LRU-bounded)."""
    if project_root in _tier_history_store:
        # Move to end (most recently used)
        _tier_history_store.move_to_end(project_root)
        return _tier_history_store[project_root]
    return None


def _tier_history_set(project_root: str, value: dict) -> None:
    """Set tier history for a project root (LRU-bounded with explicit eviction)."""
    if project_root in _tier_history_store:
        # Update existing - move to end
        _tier_history_store.move_to_end(project_root)
    elif len(_tier_history_store) >= _MAX_TIER_HISTORY:
        # Evict least recently used
        _tier_history_store.popitem(last=False)
    _tier_history_store[project_root] = value


def _validate_project_root(project_root: str) -> tuple[Optional[str], Optional[Path]]:
    """
    Validate and resolve project_root.

    Returns:
        (error_message, resolved_path)
        - If valid: (None, Path)
        - If invalid: (error_string, None)
    """
    try:
        # Resolve absolute path, resolving symlinks
        root_path = Path(project_root).resolve(strict=True)
    except (OSError, FileNotFoundError):
        return (f"Project root not found or inaccessible: {project_root}", None)

    if not root_path.is_dir():
        return (f"Project root is not a directory: {project_root}", None)

    # Ensure path is readable
    if not os.access(root_path, os.R_OK):
        return (f"Project root not readable (permission denied): {project_root}", None)

    return (None, root_path)

def _validate_file_containment(file_path: str, project_root: Path) -> Optional[str]:
    """TC-006: verify a resolved file path stays inside project_root.

    Returns None if contained, or an error string if the path escapes.
    """
    resolved = Path(file_path).resolve()
    try:
        resolved.relative_to(project_root)
    except ValueError:
        return f"File path escapes project root: {file_path}"
    return None

def _savings_pct(token_estimate: int, full_repo_estimate: int) -> float:
    """% of full-repo context saved by a token estimate. 0 when repo is empty or
    the estimate exceeds the repo (a tier-1 map can cost more than reading it)."""
    if not full_repo_estimate:
        return 0.0
    return round(max(0.0, 1 - token_estimate / full_repo_estimate) * 100, 1)


def _full_repo_tokens(project_root: str) -> int:
    """Estimate full-repo token cost (sum of raw source-file reads)."""
    return repo_budget(project_root, 0)["full_repo_estimate"]


def _budget_fields(resp: dict, full_repo_tokens: int, coverage_pct: Optional[float] = None) -> dict:
    """Add token_estimate/full_repo_estimate/savings_pct to a search-tool response.

    token_estimate = tokens of the serialized (non-error) response body.
    savings_pct = context saved vs reading the full repo. 0 when repo is empty.
    """
    tok = count_tokens(json.dumps(resp), "gpt-4")
    result = {
        "token_estimate": tok,
        "full_repo_estimate": full_repo_tokens,
        "savings_pct": _savings_pct(tok, full_repo_tokens),
    }
    if coverage_pct is not None:
        result["coverage_pct"] = coverage_pct
    return result


_TRUST_METADATA = {
    "source": "scanned_repository",
    "trust": "untrusted_repository_content",
}

def _mark_untrusted(resp: dict) -> dict:
    """TC-005: stamp repository-content trust metadata on response dicts."""
    resp.update(_TRUST_METADATA)
    return resp


# TC-001: explicit boundary markers around raw repo-derived text so an agent
# can't mistake injected comments/filenames/instructions for its own prompt.
_TRUST_BEGIN = "BEGIN UNTRUSTED REPOSITORY CONTEXT"
_TRUST_END = "END UNTRUSTED REPOSITORY CONTEXT"


def wrap_untrusted_content(text: str) -> str:
    """Wrap raw repo-derived text in explicit trust-boundary markers (TC-001)."""
    if not text:
        return text
    return f"{_TRUST_BEGIN}\n{text}\n{_TRUST_END}"


def _attach_scan_warning(resp: dict) -> dict:
    """TC-002: attach the resource-envelope partial-scan warning if any."""
    warn = _last_scan_report.get("warning")
    if warn:
        resp["scan_warning"] = warn
    return resp


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
    pre_index: Optional[str] = None,
    pre_index_max_files: int = 100,
    pre_index_include_parents: int = 0,
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
        - On success, all responses include 'source' ('scanned_repository') and 'trust' ('untrusted_repository_content') for provenance tracking.
        Or an 'error' key if an error occurred.
    """
    err, root_path = _validate_project_root(project_root)
    if err:
        return {"error": err}

    # 1. Handle and validate parameters
    # Convert token_limit to integer with fallback
    try:
        token_limit = int(token_limit) if token_limit else 8192
    except (TypeError, ValueError):
        token_limit = 8192
    
    # Ensure token_limit is positive
    if token_limit <= 0:
        token_limit = 8192
    
    # TC-007: clamp max_files server-side — prevents callers from requesting
    # absurd scan sizes (e.g. 999999999) that could exhaust resources.
    # Discovery already early-stops at 20_000 (MAX_SCAN_FILES in utils.py),
    # but clamp the param itself so downstream code never sees an absurd value.
    MAX_ALLOWED_FILES = 10000
    max_files = min(max_files, MAX_ALLOWED_FILES)
    
    chat_files_list = chat_files or []
    mentioned_fnames_set = set(mentioned_files) if mentioned_files else None
    mentioned_idents_set = set(mentioned_idents) if mentioned_idents else None

    # 2. If a specific list of other_files isn't provided, scan the whole root directory.
    # This should happen regardless of whether chat_files are present.
    effective_other_files = []
    if other_files:
        effective_other_files = other_files
    else:
        # Pre-index probe: if pre_index is given and no other_files provided, run ctags probe
        if pre_index:
            log.info(f"Probing ctags for symbol '{pre_index}' in {project_root}...")
            probed_rel_files = probe_and_narrow(
                project_root,
                pre_index,
                max_files=pre_index_max_files,
                include_parents=pre_index_include_parents
            )
            if probed_rel_files:
                log.info(f"Ctags probe matched {len(probed_rel_files)} files.")
                effective_other_files = probed_rel_files
            else:
                log.warning(f"Ctags probe found no matches for '{pre_index}', falling back to auto-scan.")
        
        if not effective_other_files:
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
    
    # TC-006: reject any file paths that resolve outside the project root
    for f in abs_chat_files + abs_other_files:
        err = _validate_file_containment(f, root_path)
        if err:
            return {"error": err}
    
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
                return _attach_scan_warning(_mark_untrusted(result))

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
                    "total_files_considered": file_report.total_files_considered,
                    "coverage_pct": file_report.coverage_pct,
                }

            token_estimate = count_tokens(map_content or "", "gpt-4")
            full_repo_estimate = _full_repo_tokens(project_root)

            # TC-008: contain output_file writes to tricorder-managed storage only.
            # A caller-controlled path with no validation could write anywhere
            # the host user has access. Resolve to an explicit output dir and
            # reject escapes.
            _TRICORDER_OUTPUT_DIR = Path(__file__).resolve().parent / ".tricorder" / "output"
            out_path = _TRICORDER_OUTPUT_DIR / Path(output_file).name
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
                "estimated_index_tokens": int(tokens_per_tag * len(ranked_tags)),
                "tier": tier,
                "format": output_format,
                "report": report_dict,
                "coverage_pct": file_report.coverage_pct,
            }
            # Advisory tier hint: T0 incomplete (truncated at budget)
            if tags_at_budget < len(ranked_tags):
                pct = round(tags_at_budget / len(ranked_tags) * 100, 1)
                result["tier_hint"] = f"T0 incomplete: {tags_at_budget}/{len(ranked_tags)} tags fit ({pct}%). Consider tier=1 or higher token_limit."
            # Advisory tier hint: upgrade from previous tier
            prev = _tier_history_get(project_root)
            if prev:
                if tier > prev["last_tier"] and prev.get("map_file"):
                    result["tier_hint"] = (
                        f"Upgrading from T{prev['last_tier']} to T{tier}. "
                        f"The T{prev['last_tier']} map at {prev['map_file']} may have been sufficient — "
                        f"only escalate tiers if the previous tier genuinely failed to answer your question."
                    )
            _tier_history_set(project_root, {"last_tier": tier, "last_format": output_format, "map_file": str(out_path)})
            return _attach_scan_warning(_mark_untrusted(result))

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
                "total_files_considered": file_report.total_files_considered,
                "coverage_pct": file_report.coverage_pct,
            }
        _tok = count_tokens(map_content or "", "gpt-4")
        _full = _full_repo_tokens(project_root)
        return _attach_scan_warning(_mark_untrusted({"map": wrap_untrusted_content(map_content), "report": report_dict,
                "token_estimate": _tok,
                "full_repo_estimate": _full,
                "savings_pct": _savings_pct(_tok, _full),
                "coverage_pct": file_report.coverage_pct}))

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
    include_references: bool = True,
    pre_index: Optional[str] = None,
    pre_index_max_files: int = 100,
    pre_index_include_parents: int = 0,
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
    err, root_path = _validate_project_root(project_root)
    if err:
        return {"error": err}

    project_root = str(root_path)

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
        # Pre-index probe: narrow the file set to files containing the probe
        # symbol (same fast path tricorder_scan uses). Prevents full-tree walks
        # on huge repos (e.g. the Linux kernel) where a blind search across
        # every file is slow and cold-cache-flaky. Mirrors --pre-index on the CLI.
        if pre_index:
            probed = probe_and_narrow(
                project_root, pre_index,
                max_files=pre_index_max_files,
                include_parents=pre_index_include_parents,
            )
            if probed:
                # probe_and_narrow returns paths relative to project_root; normalize
                # to absolute to match find_src_files() contract (the tag loop does
                # Path(file_path).relative_to(project_root), which raises on rel input).
                all_files = [str(Path(project_root) / f) for f in probed]
                
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
        return _mark_untrusted(resp)

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
    err, root_path = _validate_project_root(project_root)
    if err:
        return {"error": err}

    project_root = str(root_path)

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
        return _mark_untrusted(resp)

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
    
    # TC-006: reject file paths that escape the project root
    err = _validate_file_containment(file_path, Path(project_root))
    if err:
        return {"error": err}

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
        return _mark_untrusted(resp)

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
        return _mark_untrusted(result)

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
