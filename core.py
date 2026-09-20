"""
Tricorder class for generating repository maps.
"""

import os
import re
import sys
import threading
from pathlib import Path
# Pin project dir ahead of sys.path (mirror tricorder.py) so utils/scm resolve to THIS repo.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from typing import List, Dict, Optional, Tuple, Callable, Any
from utils import count_tokens, read_text, Tag, SymbolRecord, discover_src_files, detect_lang, ParsedQuery, repo_budget, query_variants, tokenize_identifier, levenshtein, stat_fingerprint
from cache import TagsCacheMixin, CACHE_VERSION
from parser import ParserMixin
from graph import GraphMixin
from ranking import RankingMixin
from database import DBStore
from scm import get_scm_fname
from importance import filter_important_files
from report import FileReport
from render import render_tree, to_tree


class TricorderError(Exception):
    """Base exception for Tricorder errors."""
    pass


class GrepAstNotAvailableError(TricorderError):
    """Raised when grep-ast is not available."""
    pass


# Constants
TAGS_CACHE_DIR = f".tricorder.tags.cache.v{CACHE_VERSION}"

_COVERAGE_WARN_THRESHOLD = 60.0  # percentage; can be overridden via config

# TC-004: hard wall-clock budget for a single tree-sitter parse. A pathological
# file can hang in-process parsing with no native timeout; we bound it.
_PARSER_TIMEOUT_S = float(os.environ.get("TRICORDER_PARSER_TIMEOUT_S", "5"))



class Tricorder(ParserMixin, GraphMixin, RankingMixin, TagsCacheMixin):
    """Main class for generating repository maps.

    Per-file tags cache methods (get_tags, load_tags_cache, tags_cache_error,
    _cache_dir) live in cache.py (TagsCacheMixin) — see cache.py docstring.
    discover_src_files is in utils.py, not duplicated here.
    """
    
    def __init__(
        self,
        map_tokens: int = 1024,
        root: str = None,
        token_counter_func: Callable[[str], int] = count_tokens,
        file_reader_func: Callable[[str], Optional[str]] = read_text,
        output_handler_funcs: Dict[str, Callable] = None,
        repo_content_prefix: Optional[str] = None,
        verbose: bool = False,
        max_context_window: Optional[int] = None,
        map_mul_no_files: int = 8,
        refresh: str = "auto",
        exclude_unranked: bool = False,
        context_lines: int = 0,
        exclude_untagged: bool = False,
        exclude_globs: Optional[List[str]] = None,
        cache_size_limit: int = 100 * 1024 * 1024,  # 100MB default
        cache_eviction_policy: str = "least-recently-used",
        cache_ttl: Optional[int] = None,
        full_map: bool = False,
        use_db: bool = True,
        db_path: Optional[str] = None,
        db_read_only: bool = False,
    ):
        """Initialize Tricorder instance.

        db_read_only: open an existing db_path frozen read-only (diff
        readers). Never combine with scan/write paths; requires a real
        path, raises ValueError through DBStore otherwise."""
        self.map_tokens = map_tokens
        self.max_map_tokens = map_tokens
        self.root = Path(root or os.getcwd()).resolve()
        self.token_count_func_internal = token_counter_func
        self.read_text_func_internal = file_reader_func
        self.repo_content_prefix = repo_content_prefix
        self.verbose = verbose
        self.max_context_window = max_context_window
        self.map_mul_no_files = map_mul_no_files
        self.refresh = refresh
        self.exclude_unranked = exclude_unranked
        self.context_lines = context_lines
        self.exclude_untagged = exclude_untagged
        self.exclude_globs = exclude_globs
        self.cache_size_limit = cache_size_limit
        self.cache_eviction_policy = cache_eviction_policy
        self.cache_ttl = cache_ttl
        self.full_map = full_map
        
        # Flat-memory parse store (SPEC_db_map Goal 3). DB-backed ranking is the
        # default execution path (use_db=True); --no-db selects the legacy path.
        self._db_active = bool(use_db)
        self._db_path = db_path
        self._db_store: Optional[DBStore] = None
        if self._db_active:
            self._db_store = DBStore(db_path, read_only=db_read_only)
        
        # Set up output handlers
        if output_handler_funcs is None:
            output_handler_funcs = {
                'info': print,
                'warning': print,
                'error': print
            }
        self.output_handlers = output_handler_funcs
        
        # Initialize caches
        self.tree_cache = {}
        self.tree_context_cache = {}
        self.map_cache = {}
        self._cross_file_index_cache: Optional[Tuple[Dict, Dict]] = None
        
        # Thread safety locks for cache access
        self._tags_cache_lock = threading.RLock()
        self._import_index_lock = threading.RLock()
        self._cross_file_index_lock = threading.RLock()
        
        # Load persistent tags cache
        self.load_tags_cache()

    def close(self):
        """Checkpoint and close the DB store, releasing the sqlite handle.

        Idempotent. After close, scan/query methods that need the DB will
        fail — this instance is done. The CLI calls it on every exit path
        (so a later --diff sees this scan); the MCP server calls it for
        per-call instances and evicted cache entries."""
        store, self._db_store = self._db_store, None
        if store is not None:
            store.close()
    
    def token_count(self, text: str) -> int:
        """Count tokens in text with sampling optimization for long texts."""
        if not text:
            return 0
        
        len_text = len(text)
        if len_text < 200:
            return self.token_count_func_internal(text)
        
        # Sample for longer texts
        lines = text.splitlines(keepends=True)
        num_lines = len(lines)
        
        step = max(1, num_lines // 100)
        sampled_lines = lines[::step]
        sample_text = "".join(sampled_lines)
        
        if not sample_text:
            return self.token_count_func_internal(text)
        
        sample_tokens = self.token_count_func_internal(sample_text)
        
        est_tokens = (sample_tokens / len(sample_text)) * len_text
        return int(est_tokens)
    
    def get_rel_fname(self, fname: str) -> str:
        """Get relative filename from absolute path."""
        try:
            return str(Path(fname).relative_to(self.root))
        except ValueError:
            return fname

    def _within_root(self, resolved_path: str) -> bool:
        """True when a resolved absolute path sits inside the repo root.

        Symlinks (or explicit paths) that resolve outside the root must
        never enter the DB: get_rel_fname() would return the absolute
        path unchanged, leaking host paths into stored rels and served
        maps. Callers skip such files with a warning instead.
        """
        try:
            Path(resolved_path).relative_to(self.root)
            return True
        except ValueError:
            return False
    
    def get_mtime(self, fname: str) -> Optional[float]:
        """Get file modification time."""
        try:
            return os.path.getmtime(fname)
        except FileNotFoundError:
            self.output_handlers['warning'](f"File not found: {fname}")
            return None

    def diff_against_index(
        self,
        include_tags: bool = True,
        max_tags_per_file: int = 50,
    ) -> Dict[str, Any]:
        """Compare the working tree against the DB's recorded file_state.

        Returns a delta map::
            {
              "added": [rel, ...],      # on disk, not in index
              "modified": [rel, ...],   # (size, mtime) differs from index
              "deleted": [rel, ...],    # in index, not on disk
              "tags": {rel: [tag dicts]},  # per-file tag HEADS for
                                           # added+modified (capped)
              "tag_counts": {rel: int},    # exact per-file tag totals
              "tags_omitted": {rel: int},  # heads cut short: total - kept
              "tags_truncated": bool,      # any head capped
              "indexed": bool,          # False when the DB was never scanned
            }

        Render diet: a concise diff must not ship a whole-repo tag
        inventory. Per-file tag lists are capped at max_tags_per_file
        (0 = unlimited); exact totals stay available via tag_counts and
        every cut is explicit via tags_omitted/tags_truncated.
        include_tags=False skips tag parsing entirely (file lists only).
        When the index is absent (indexed=False) no tags are parsed at
        all: without a baseline the file list IS the delta, and a
        full-repo inventory would be a scan, not a diff.

        Read-only: it never updates the index. When the DB has no file_state
        (never scanned, or --no-db), every file reports as added and
        indexed=False.
        """
        # The index DB itself (plus sqlite sidecars) is the thing being
        # compared against, not working-tree content: invisible to the diff
        # in both directions, so a hand-placed --db-path inside the root
        # doesn't report db.idx/-wal/-shm as added/modified forever.
        db_rels = set()
        if self._db_path:
            dbp = str(Path(self._db_path).resolve())
            for p in (dbp, dbp + "-wal", dbp + "-shm", dbp + "-journal"):
                try:
                    db_rels.add(self.get_rel_fname(p))
                except Exception:
                    pass

        stored: Dict[str, Tuple[int, int]] = {}
        if self._db_store is not None:
            try:
                stored = self._db_store.get_file_state()
            except Exception:
                stored = {}
        stored = {rel: v for rel, v in stored.items() if rel not in db_rels}

        current: Dict[str, Tuple[str, int, int]] = {}
        for fpath in discover_src_files(str(self.root), use_gitignore=True,
                                        exclude_globs=self.exclude_globs):
            try:
                st = os.stat(fpath)
            except OSError:
                continue
            # Resolve symlinks before the rel computation: the scan path
            # stores resolved rels (Path.resolve()), so an unresolved
            # symlink would otherwise report as "Added" on every diff.
            # Files resolving outside the root are skipped entirely (same
            # rule as the scan path): they must never appear in the delta
            # with absolute host paths.
            try:
                resolved = str(Path(fpath).resolve())
            except Exception:
                resolved = fpath
            if not self._within_root(resolved):
                continue
            try:
                rel = self.get_rel_fname(resolved)
            except Exception:
                rel = self.get_rel_fname(fpath)
            if rel in db_rels:
                continue
            current[rel] = (fpath, *stat_fingerprint(st))

        added, modified, deleted = [], [], []
        for rel, (_fpath, size, mtime) in current.items():
            if rel not in stored:
                added.append(rel)
            elif stored[rel] != (size, mtime):
                modified.append(rel)
        for rel in stored:
            if rel not in current:
                deleted.append(rel)

        tags: Dict[str, list] = {}
        tag_counts: Dict[str, int] = {}
        tags_omitted: Dict[str, int] = {}
        indexed = bool(stored)
        if include_tags and indexed:
            for rel in sorted(added + modified):
                fpath = current[rel][0]
                try:
                    ftags = self.get_tags(fpath, rel)
                    all_tags = [t._asdict() for t in ftags]
                except Exception:
                    all_tags = []
                tag_counts[rel] = len(all_tags)
                if max_tags_per_file and len(all_tags) > max_tags_per_file:
                    tags[rel] = all_tags[:max_tags_per_file]
                    tags_omitted[rel] = len(all_tags) - max_tags_per_file
                else:
                    tags[rel] = all_tags

        return {
            "added": sorted(added),
            "modified": sorted(modified),
            "deleted": sorted(deleted),
            "tags": tags,
            "tag_counts": tag_counts,
            "tags_omitted": tags_omitted,
            "tags_truncated": bool(tags_omitted),
            "indexed": indexed,
        }

    def search_identifiers(
        self,
        query: str,
        max_results: int = 50,
        context_lines: int = 1,
        include_definitions: bool = True,
        include_references: bool = True,
        search_mode: str = "substring",  # "exact", "substring", "regex"
        files: Optional[List[str]] = None,
    ) -> Tuple[List[Dict[str, Any]], bool]:
        """Search identifier tags (definitions + references) for a query.

        Pure core behind the tricorder_detect MCP tool and the --detect CLI
        flag. Returns (results, rescue_used) where each result is
        {file, line, name, kind, context, quality}. Raises ValueError on an
        invalid regex pattern.

        Render diet: context defaults to ±1 line (plus blank-line
        stripping). The match line ±1 disambiguates hits; file/line/name
        stay exact, so a thinner window loses no accuracy — escalate to
        symbols/detail when the window is not enough.
        """
        # Empty query would substring-match every identifier; return no
        # matches instead of shipping arbitrary tags as "exact" hits.
        if not query:
            return [], False

        # Honor the caller's cap (and a 200 hard cap mirroring
        # search_symbols): the rescue pool below intentionally
        # over-collects (2x) for re-ranking headroom, so clamp here and
        # trim again after the rescue re-sort.
        max_results = min(max(max_results, 1), 200)
        if search_mode not in ("exact", "substring", "regex"):
            raise ValueError(
                f"Invalid search_mode: {search_mode}. Must be 'exact', 'substring', or 'regex'.")

        root = str(self.root)
        all_files = files if files is not None else discover_src_files(
            root, use_gitignore=True, exclude_globs=self.exclude_globs)

        # Get all tags (definitions and references) for all files
        all_tags = []
        for file_path in all_files:
            rel_path = self.get_rel_fname(file_path)
            all_tags.extend(self.get_tags(file_path, rel_path))

        # Filter tags based on search query and options
        matching_tags = []
        query_lower = query.lower()

        # Compile regex if needed
        regex_pattern = None
        if search_mode == "regex":
            try:
                regex_pattern = re.compile(query, re.IGNORECASE)
            except re.error as e:
                raise ValueError(f"Invalid regex pattern: {e}")

        for tag in all_tags:
            name = tag.name
            name_lower = name.lower()

            match = False
            if search_mode == "exact":
                match = name_lower == query_lower
            elif search_mode == "substring":
                match = query_lower in name_lower
            elif search_mode == "regex":
                match = bool(regex_pattern.search(name))

            if match:
                if (tag.kind == "def" and include_definitions) or \
                   (tag.kind == "ref" and include_references):
                    matching_tags.append(tag)

        # Sort by relevance (definitions first, then references)
        matching_tags.sort(key=lambda x: (x.kind != "def", x.name.lower().find(query_lower)))

        # Limit results
        matching_tags = matching_tags[:max_results]

        # Retrieve-0 rescue: the substring query matched nothing (e.g. because
        # the agent typed a decorated/qualified/differently-cased name). Retry
        # over deterministic orthographic variants so a dead-end lookup becomes
        # a set of near-lookalike candidates instead of an empty result. Flag
        # them 'fuzzy' so the consumer knows they are not exact-name hits and
        # must be verified against source. No LLM, reproducible.
        rescue_used = False
        if not matching_tags and query:
            seen = set()
            for cand in query_variants(query):
                if len(cand) < 2:
                    continue
                cand_l = cand.lower()
                for tag in all_tags:
                    if id(tag) in seen:
                        continue
                    if cand_l in tag.name.lower():
                        if (tag.kind == "def" and include_definitions) or \
                           (tag.kind == "ref" and include_references):
                            matching_tags.append(tag)
                            seen.add(id(tag))
                if len(matching_tags) >= max_results * 2:
                    break
            if not matching_tags:
                # Edit-distance + token-overlap pass (typos, affixes like
                # serial->serialize that separators/case can't bridge).
                # ponytail: linear scan, early-exit distance; fine at rescue
                # scale (fires only on empty). No index until measured slow.
                qcore = "".join(tokenize_identifier(query)) or query.lower()
                qtok = set(tokenize_identifier(query))
                scored = []
                for tag in all_tags:
                    if not ((tag.kind == "def" and include_definitions) or
                            (tag.kind == "ref" and include_references)):
                        continue
                    tn = tag.name.lower()
                    tt = tokenize_identifier(tag.name)
                    tj = "".join(tt)
                    d = min(levenshtein(qcore, tn), levenshtein(qcore, tj))
                    overlap = len(qtok & set(tt)) if qtok else 0
                    if d <= 2 or (qtok and overlap * 2 >= len(qtok)):
                        scored.append((d, -overlap, tag.kind != "def", tn, tag))
                scored.sort(key=lambda s: (s[0], s[1], s[2], s[3]))
                matching_tags = [s[4] for s in scored[:max_results * 2]]
            if matching_tags:
                rescue_used = True
            if rescue_used:
                qcore = "".join(tokenize_identifier(query)) or query.lower()
                matching_tags.sort(key=lambda t: (
                    min(levenshtein(qcore, t.name.lower()),
                        levenshtein(qcore, "".join(tokenize_identifier(t.name)))),
                    t.kind != "def", t.name.lower()))
                # Trim the 2x rescue pool back to the caller's cap.
                del matching_tags[max_results:]

        # Format results with context
        results = []
        for tag in matching_tags:
            file_path = str(Path(root) / tag.rel_fname)

            # Calculate context range based on context_lines parameter
            start_line = max(1, tag.line - context_lines)
            end_line = tag.line + context_lines
            context_range = list(range(start_line, end_line + 1))

            # Render diet: blank/whitespace-only lines carry no code
            # information but dominate context bytes (measured ~75% of a
            # detect payload, mostly empty lines). Drop them from the
            # window; the match line is always kept and survivors keep
            # their numbers, so no positional accuracy is lost.
            code_lines = self.get_file_text(file_path).splitlines()
            context_range = [
                ln for ln in context_range
                if ln == tag.line
                or (1 <= ln <= len(code_lines) and code_lines[ln - 1].strip())
            ] or [tag.line]

            context = self.render_tree(
                file_path,
                tag.rel_fname,
                context_range
            )

            # A match is a match even when context rendering yields nothing
            # (e.g. the file became unreadable between tagging and render):
            # never drop the symbol, ship it with empty context instead.
            results.append({
                "file": tag.rel_fname,
                "line": tag.line,
                "name": tag.name,
                "kind": tag.kind,
                "context": context or "",
                "quality": "fuzzy" if rescue_used else "exact"
            })

        return results, rescue_used

    def search_symbols(
        self,
        query: str = "",
        type: Optional[str] = None,
        file: Optional[str] = None,
        limit: int = 50,
        files: Optional[List[str]] = None,
    ) -> Tuple[List[Dict[str, Any]], bool]:
        """Search code symbols by name, type, or file path.

        Pure core behind the tricorder_symbols MCP tool and the --symbols CLI
        flag. Returns (results, rescue) where each result is a symbol record
        dict (flagged 'fuzzy' when the retrieve-0 rescue fired).
        """
        # Enforce limit cap
        limit = min(max(limit, 1), 200)

        root = str(self.root)
        all_files = files if files is not None else discover_src_files(
            root, use_gitignore=True, exclude_globs=self.exclude_globs)
        all_symbols = []

        for file_path in all_files:
            rel_path = self.get_rel_fname(file_path)

            # File filter - match against relative path (POSIX normalized)
            if file and file.lower() not in rel_path.replace('\\', '/').lower():
                continue

            all_symbols.extend(self.get_symbols(file_path, rel_path))

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

        # Retrieve-0 rescue (mirror search_identifiers): retry over orthographic
        # variants when the plain substring query matched nothing, so
        # decorated/cased lookups still surface near-lookalike symbols.
        # Flagged 'fuzzy'.
        rescue = False
        if query and not results:
            seen = set()
            for cand in query_variants(query):
                if len(cand) < 2:
                    continue
                cand_l = cand.lower()
                for sym in all_symbols:
                    if id(sym) in seen:
                        continue
                    if type and sym.type != type:
                        continue
                    if cand_l in sym.name.lower():
                        results.append(sym.to_dict())
                        seen.add(id(sym))
                if len(results) >= limit * 2:
                    break
            if not results:
                # Edit-distance + token-overlap pass (mirror search_identifiers).
                qcore = "".join(tokenize_identifier(query)) or query.lower()
                qtok = set(tokenize_identifier(query))
                scored = []
                for sym in all_symbols:
                    if type and sym.type != type:
                        continue
                    sn = sym.name.lower()
                    st = tokenize_identifier(sym.name)
                    sj = "".join(st)
                    d = min(levenshtein(qcore, sn), levenshtein(qcore, sj))
                    overlap = len(qtok & set(st)) if qtok else 0
                    if d <= 2 or (qtok and overlap * 2 >= len(qtok)):
                        scored.append((d, -overlap, sym.type, sn, sym))
                scored.sort(key=lambda s: (s[0], s[1], s[2], s[3]))
                results = [s[4].to_dict() for s in scored[:limit * 2]]
            if results:
                rescue = True
            if rescue:
                qcore = "".join(tokenize_identifier(query)) or query.lower()

                def _sdist(r_):
                    return min(levenshtein(qcore, r_["name"].lower()),
                               levenshtein(qcore, "".join(tokenize_identifier(r_["name"]))))
                results.sort(key=lambda r_: (_sdist(r_), r_["type"], r_["name"].lower()))

        # Apply limit
        results = results[:limit]

        if rescue:
            for r_ in results:
                r_["quality"] = "fuzzy"

        return results, rescue
    
