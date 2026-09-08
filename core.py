"""
Tricorder class for generating repository maps.
"""

import os
import sys
import fnmatch
import threading
import hashlib
from pathlib import Path
# Pin project dir ahead of sys.path (mirror tricorder.py) so utils/scm resolve to THIS repo.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from collections import namedtuple, defaultdict
from typing import List, Dict, Set, Optional, Tuple, Callable, Any, Union
from dataclasses import dataclass
import networkx as nx
from utils import count_tokens, read_text, Tag, SymbolRecord, discover_src_files, detect_lang, ParsedQuery, repo_budget
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
    ):
        """Initialize Tricorder instance."""
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
        
        # Flat-memory parse store (SPEC_db_map Goal 3). off by default — the
        # default execution path stays byte-identical until the DB path is proven.
        self._db_active = bool(use_db)
        self._db_path = db_path
        self._db_store: Optional[DBStore] = None
        if self._db_active:
            self._db_store = DBStore(db_path)
        
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
    
    def get_mtime(self, fname: str) -> Optional[float]:
        """Get file modification time."""
        try:
            return os.path.getmtime(fname)
        except FileNotFoundError:
            self.output_handlers['warning'](f"File not found: {fname}")
            return None
    
