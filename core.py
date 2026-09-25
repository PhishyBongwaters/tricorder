"""
Tricorder class for generating repository maps.
"""

import os
import re
import math
import sys
import threading
from bisect import bisect_left, bisect_right
from pathlib import Path
# Pin project dir ahead of sys.path (mirror tricorder.py) so utils/scm resolve to THIS repo.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from typing import List, Dict, Optional, Tuple, Callable, Any
from utils import count_tokens, read_text, Tag, SymbolRecord, discover_src_files, detect_lang, ParsedQuery, repo_budget, query_variants, tokenize_identifier, levenshtein, stat_fingerprint, canonical_token, NL_QUERY_STOPWORDS, rescue_query_tokens, _INFLECTION_EXCEPTIONS
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

# Bloat diet: symbols listings are the cheap detect -> symbols -> detail hop;
# docstrings longer than this are cut to a word boundary with an explicit
# docstring_omitted count. Full text remains available via detail.
_LISTING_DOCSTRING_CAP = 200


def _interleave_by_file(items, key, limit):
    """Round-robin items across files, preserving in-file order.

    A capped detect list ranked purely by name score can be monopolized by
    one file (e.g. ten parseExpr* declarations in a header), crowding out
    the definition sites in other files that an agent actually needs.
    Interleaving keeps the global top hit first (its file leads the first
    round) while guaranteeing cross-file recall inside the same result
    budget — no extra tokens. Deterministic: file order is first-appearance
    order in the already-ranked input.
    """
    buckets = {}
    order = []
    for it in items:
        f = key(it)
        if f not in buckets:
            buckets[f] = []
            order.append(f)
        buckets[f].append(it)
    out = []
    round_i = 0
    while len(out) < limit:
        progressed = False
        for f in order:
            if round_i < len(buckets[f]) and len(out) < limit:
                out.append(buckets[f][round_i])
                progressed = True
        if not progressed:
            break
        round_i += 1
    return out



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

        # Per-render file-text memo (see _read_text_memoized). Thread-local:
        # MCP threads share one Tricorder per root, so each concurrent
        # call gets its own memo. Active only for the duration of one
        # get_ranked_tags_map_uncached build, then cleared — never a
        # cross-call cache, so edits between calls always re-read.
        self._render_memo = threading.local()
        
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
    
    def _read_text_memoized(self, path: str) -> Optional[str]:
        """File text, memoized while a map render is active.

        get_ranked_tags_map_uncached activates the memo for the whole fit
        loop so its ~log2(N) to_tree probes share one read per file
        instead of re-reading every selected file twice per probe
        (line-count precompute + body render). Outside a render the memo
        is absent and this is a plain delegated read — detail/detect
        paths are unaffected. Thread-local, so concurrent calls sharing
        this instance never share entries.
        """
        memo = getattr(self._render_memo, 'cache', None)
        if memo is None:
            return self.read_text_func_internal(path)
        if path not in memo:
            memo[path] = self.read_text_func_internal(path)
        return memo[path]

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
        max_results: int = 10,
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

        # Sort by relevance (definitions first, then references), then
        # interleave across files so a single file's many same-name hits
        # (e.g. ten parseExpr* declarations in one header) cannot crowd
        # the definition sites in other files out of the capped budget.
        matching_tags.sort(key=lambda x: (x.kind != "def", x.name.lower().find(query_lower), x.rel_fname, x.line))

        # Limit results (interleaved: global top hit stays first).
        matching_tags = _interleave_by_file(matching_tags, lambda t: t.rel_fname, max_results)

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
                # Language keywords ("func", ...) are syntax, not signal:
                # score the stripped core/tokens so a keyword-loaded query
                # cannot majority-match or typo-match on the keyword.
                qcore, qtok = rescue_query_tokens(query)
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
                    # Strict majority: a 2-token near-miss sharing one token
                    # used to rescue whole junk families (e.g. every *ssa*
                    # test helper for "compileSSA"). Edit-distance still
                    # catches typos; overlap needs a real majority.
                    if d <= 2 or (qtok and overlap * 2 > len(qtok)):
                        scored.append((d, -overlap, tag.kind != "def", tn, tag))
                scored.sort(key=lambda s: (s[0], s[1], s[2], s[3], s[4].rel_fname, s[4].line))
                matching_tags = [s[4] for s in scored[:max_results * 2]]
            if matching_tags:
                rescue_used = True
            if rescue_used:
                qcore, _ = rescue_query_tokens(query)
                matching_tags.sort(key=lambda t: (
                    min(levenshtein(qcore, t.name.lower()),
                        levenshtein(qcore, "".join(tokenize_identifier(t.name)))),
                    t.kind != "def", t.name.lower(), t.rel_fname, t.line))
                # Trim the 2x rescue pool back to the caller's cap
                # (interleaved across files, same as the main path).
                matching_tags = _interleave_by_file(
                    matching_tags, lambda t: t.rel_fname, max_results)

        # Tier 4: content-backed symbol search for natural-language queries.
        # Name-only tiers cannot bridge "enter the exit stack" ->
        # _solve_generator: the tokens live in docstrings, bodies, and
        # call sites, not in the identifier. Fires ONLY when every name
        # tier came back empty, so exact/substring/fuzzy behavior is
        # unchanged. Deterministic, stdlib-only: weighted token overlap
        # over the def name (3x), its own source span (1x), and caller
        # lines (1x, capped). Flagged quality "content".
        content_used = False
        if not matching_tags and query and include_definitions:
            matching_tags = self._content_search_tags(
                query, all_tags, max_results)
            content_used = bool(matching_tags)

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
                "quality": ("content" if content_used else
                            "fuzzy" if rescue_used else "exact")
            })

        return results, (rescue_used or content_used)

    # Tier-4 tuning: minimum bar for a content-backed candidate. The
    # fraction keeps long NL queries honest (a random def will not cover
    # half of 7+ distinctive tokens); the absolute floor keeps 1-2 token
    # queries from matching on a single body word, while still letting
    # short span-only queries (3-4 tokens) through on full coverage.
    # Scores are IDF-weighted floats, but idf >= 1.0 always, so the old
    # integer floor semantics carry over as a lower bound.
    _CONTENT_MIN_FRACTION = 0.5
    _CONTENT_MIN_SCORE = 3
    _CONTENT_SPAN_LINES = 80
    _CONTENT_MAX_CALLERS = 8
    _CONTENT_MAX_CALLEES = 4

    def _content_search_tags(self, query, all_tags, max_results):
        """Rank def tags by natural-language token overlap (tier 4).

        Fires only when every name-based tier returned empty. Scores each
        definition by IDF-weighted overlap of the query's content tokens
        (stopwords stripped, synonym-canonicalized, plural-insensitive)
        against three token sources: the def's own name (3x, strict
        token match), its source span (1x, substring so unsplittable
        compounds like "asynccontextmanager" still match), and its
        caller lines (1x, substring, capped), and the source spans of the
        definitions it directly references (0.5x, one level only, capped
        at 4 — same-file definitions are preferred when resolving a
        referenced name, with a deterministic global-name fallback for
        cross-file calls). Each
        token's contribution
        is scaled by its inverse document frequency across the scanned
        definitions, so rare discriminative terms ("operationId",
        "yield", "dependency") outweigh ubiquitous ones ("build",
        "path", "get"): a def matching the query's distinctive words
        outranks one matching only its filler. Ranking is coverage-first:
        candidates covering more of the query's distinct concepts with
        their OWN evidence (name/span/caller) come first ((-matched,
        -score, name, file, line)); the IDF-weighted score breaks ties,
        so among equal-coverage candidates the one matching the rarer,
        more discriminative terms still wins. Callee evidence adds score
        only — never coverage — so a hub calling many helpers cannot win
        on borrowed concepts. Fully
        deterministic: candidates are visited in (file, line) order.
        Returns list[Tag].
        """
        qtok = []
        for t in tokenize_identifier(query):
            if len(t) < 2 or t in NL_QUERY_STOPWORDS:
                continue
            c = canonical_token(t)
            if c not in qtok:
                qtok.append(c)
        if not qtok:
            return []

        def _match(q, blob):
            # Plural-insensitive. The inflection exceptions ("news" is
            # not "new") are honored in both directions so the matchers
            # stay consistent with canonical_token.
            if q in blob:
                return True
            if q + "s" not in _INFLECTION_EXCEPTIONS and q + "s" in blob:
                return True
            return (len(q) > 3 and q.endswith("s")
                    and q not in _INFLECTION_EXCEPTIONS and q[:-1] in blob)

        def _match_blob(q, blob_text):
            # Substring over the span/caller text: catches unsplittable
            # compounds like "asynccontextmanager" for query "manager".
            # Space-joined so matches never span token boundaries. The
            # inflection exceptions ("news" is not "new") are honored in
            # the plural strip, matching canonical_token's rule.
            if q in blob_text:
                return True
            if (q + "s" not in _INFLECTION_EXCEPTIONS
                    and q + "s" in blob_text):
                return True
            return (len(q) > 3 and q.endswith("s")
                    and q not in _INFLECTION_EXCEPTIONS
                    and q[:-1] in blob_text)

        # Group defs per file in deterministic order; tokenize every
        # involved file's lines once (defs' files and callers' files —
        # a caller may live in a file with no defs of its own).
        defs_by_file = {}
        for tag in all_tags:
            if tag.kind == "def":
                defs_by_file.setdefault(tag.rel_fname, []).append(tag)
        refs_by_name = {}
        for tag in all_tags:
            if tag.kind == "ref":
                refs_by_name.setdefault(tag.name, []).append(tag)

        file_tok_lines = {}
        for rel_fname in sorted(
                set(defs_by_file) | {t.rel_fname for v in refs_by_name.values()
                                     for t in v}):
            file_path = str(Path(self.root) / rel_fname)
            try:
                lines = self.get_file_text(file_path).splitlines()
            except (OSError, UnicodeDecodeError):
                continue
            file_tok_lines[rel_fname] = [
                {canonical_token(w) for w in tokenize_identifier(l)}
                for l in lines
            ]
        scored = []
        # Pass 1a: per-definition evidence records. Each record holds the
        # def tag, its span line range, and the token sets for its name
        # and own source span. Callee evidence (pass 1b) reuses these
        # records, so every definition's span is tokenized exactly once.
        # records: (rel_fname, dtag, start, end, name_set, span_set).
        records = []
        by_file_name = {}  # (rel_fname, defname) -> record index; full
                           # names and short names both resolve, first
                           # definition in line order wins ties.
        for rel_fname in sorted(defs_by_file):
            defs = sorted(defs_by_file[rel_fname], key=lambda t: t.line)
            tok_lines = file_tok_lines.get(rel_fname)
            if tok_lines is None:
                continue
            n_lines = len(tok_lines)
            for i, dtag in enumerate(defs):
                start = dtag.line
                end = (defs[i + 1].line - 1 if i + 1 < len(defs)
                       else n_lines)
                end = min(end, start - 1 + self._CONTENT_SPAN_LINES)
                span_set = set()
                for ln in range(start, min(end + 1, n_lines + 1)):
                    span_set.update(tok_lines[ln - 1])
                short = dtag.name.split("::")[-1]
                name_set = {canonical_token(w)
                            for w in tokenize_identifier(short)}
                idx = len(records)
                records.append((rel_fname, dtag, start, end,
                                name_set, span_set))
                by_file_name.setdefault((rel_fname, dtag.name), idx)
                by_file_name.setdefault((rel_fname, short), idx)
        # Global fallback for cross-file callee resolution, in the same
        # deterministic (file, line) visit order. Same-file names always
        # win (checked first); this only fires for references no
        # same-file definition satisfies — e.g. _solve_generator's call
        # to contextmanager_in_threadpool, which lives in another module.
        by_global_name = {}
        for idx, (rel_fname, dtag, _s, _e, _n, _sp) in enumerate(records):
            by_global_name.setdefault(dtag.name, idx)
            by_global_name.setdefault(dtag.name.split("::")[-1], idx)

        # Refs per file, sorted by line, for callee lookup: a callee of
        # a definition is a definition whose name appears as a ref tag
        # inside the definition's span. Same-file definitions are
        # preferred; a global name index is the fallback for cross-file
        # calls (e.g. _solve_generator -> contextmanager_in_threadpool).
        # Either way the bound holds: one level, capped, callee spans are
        # never expanded recursively.
        refs_by_file = {}
        for tag in all_tags:
            if tag.kind == "ref":
                refs_by_file.setdefault(tag.rel_fname, []).append(tag)
        ref_lines = {}
        for rel, rtags in refs_by_file.items():
            rtags.sort(key=lambda t: t.line)
            ref_lines[rel] = [t.line for t in rtags]

        # Pass 1b: per-definition token hits plus document frequency of
        # each query token (a "document" is one definition's combined
        # name/span/caller/callee evidence, matched with the same
        # semantics). Callee evidence is one level only: a callee
        # contributes its own span tokens, never expanded recursively.
        # A token counts once, at its highest-precedence source
        # (name > span > caller > callee).
        def_hits = []
        doc_freq = {}
        for idx, (rel_fname, dtag, start, end, name_set,
                  span_set) in enumerate(records):
            short = dtag.name.split("::")[-1]
            caller_set = set()
            callers = refs_by_name.get(dtag.name, [])
            if dtag.name != short:
                callers = callers + refs_by_name.get(short, [])
            for rtag in sorted(callers,
                               key=lambda t: (t.rel_fname, t.line)
                               )[:self._CONTENT_MAX_CALLERS]:
                rlines = file_tok_lines.get(rtag.rel_fname)
                if rlines is None:
                    continue
                for ln in (rtag.line - 1, rtag.line, rtag.line + 1):
                    if 1 <= ln <= len(rlines):
                        caller_set.update(rlines[ln - 1])
            callee_set = set()
            rtags = refs_by_file.get(rel_fname, [])
            if rtags:
                lines = ref_lines[rel_fname]
                lo = bisect_left(lines, start)
                hi = bisect_right(lines, end)
                seen_callees = set()
                for rtag in rtags[lo:hi]:
                    cidx = by_file_name.get((rel_fname, rtag.name))
                    if cidx is None:
                        cidx = by_global_name.get(rtag.name)
                    if (cidx is None or cidx == idx
                            or cidx in seen_callees):
                        continue
                    seen_callees.add(cidx)
                    callee_set.update(records[cidx][5])
                    if len(seen_callees) >= self._CONTENT_MAX_CALLEES:
                        break
            # Space-joined text for substring (compound) matching.
            span_text = " ".join(sorted(span_set))
            caller_text = " ".join(sorted(caller_set))
            callee_text = " ".join(sorted(callee_set))
            name_hits = {q for q in qtok if _match(q, name_set)}
            span_hits = {q for q in qtok
                         if q not in name_hits
                         and _match_blob(q, span_text)}
            caller_hits = {q for q in qtok
                           if q not in name_hits and q not in span_hits
                           and _match_blob(q, caller_text)}
            callee_hits = {q for q in qtok
                           if q not in name_hits and q not in span_hits
                           and q not in caller_hits
                           and _match_blob(q, callee_text)}
            for q in name_hits | span_hits | caller_hits | callee_hits:
                doc_freq[q] = doc_freq.get(q, 0) + 1
            def_hits.append((dtag, name_hits, span_hits, caller_hits,
                             callee_hits))
        n_defs = len(def_hits)
        if n_defs == 0:
            return []
        # Smoothed IDF: 1.0 for a token in every definition, growing
        # logarithmically as it gets rarer. Deterministic (math.log).
        idf = {q: math.log((n_defs + 1) / (doc_freq.get(q, 0) + 1)) + 1.0
               for q in qtok}
        # Pass 2: IDF-weighted scoring. Coverage counts only the
        # definition's OWN evidence (name, own span, caller lines):
        # callee hits are corroborating evidence, worth 0.5x in the
        # score, but they never inflate coverage — otherwise a hub that
        # calls many helpers wins on borrowed concepts. The coverage
        # fraction and the absolute floor are unchanged: idf >= 1.0, so
        # the old floor semantics carry over as a lower bound.
        for dtag, name_hits, span_hits, caller_hits, callee_hits in def_hits:
            own_hits = name_hits | span_hits | caller_hits
            matched = len(own_hits)
            if matched / len(qtok) < self._CONTENT_MIN_FRACTION:
                continue
            score = (sum(idf[q] * 3 for q in name_hits)
                     + sum(idf[q] for q in span_hits | caller_hits)
                     + sum(idf[q] * 0.5 for q in callee_hits))
            if score >= self._CONTENT_MIN_SCORE:
                scored.append((-matched, -score, dtag.name.lower(),
                               dtag.rel_fname, dtag.line, dtag))
        scored.sort(key=lambda s: s[:5])
        # Interleave across files (same recall rationale as search_identifiers)
        # instead of the old dominated double slice.
        picked = _interleave_by_file(
            scored[:max_results * 2], lambda s: s[5].rel_fname, max_results)
        return [s[5] for s in picked]

    def search_symbols(
        self,
        query: str = "",
        type: Optional[str] = None,
        file: Optional[str] = None,
        limit: int = 10,
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

        # Sort: definitions first, then by name. File+line tie-break keeps
        # the order independent of file-discovery sequence (filesystems
        # traverse in different orders per machine).
        results.sort(key=lambda x: (x["type"], x["name"].lower(), x["file"], x["line"]))

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
                # Language keywords ("func", ...) are syntax, not signal:
                # score the stripped core/tokens so a keyword-loaded query
                # cannot majority-match or typo-match on the keyword.
                qcore, qtok = rescue_query_tokens(query)
                scored = []
                for sym in all_symbols:
                    if type and sym.type != type:
                        continue
                    sn = sym.name.lower()
                    st = tokenize_identifier(sym.name)
                    sj = "".join(st)
                    d = min(levenshtein(qcore, sn), levenshtein(qcore, sj))
                    overlap = len(qtok & set(st)) if qtok else 0
                    # Strict majority (mirror search_identifiers): sharing
                    # half the query tokens is not a rescue, it's junk.
                    if d <= 2 or (qtok and overlap * 2 > len(qtok)):
                        scored.append((d, -overlap, sym.type, sn, sym))
                scored.sort(key=lambda s: (s[0], s[1], s[2], s[3], s[4].file, s[4].line))
                results = [s[4].to_dict() for s in scored[:limit * 2]]
            if results:
                rescue = True
            if rescue:
                qcore, _ = rescue_query_tokens(query)

                def _sdist(r_):
                    return min(levenshtein(qcore, r_["name"].lower()),
                               levenshtein(qcore, "".join(tokenize_identifier(r_["name"]))))
                results.sort(key=lambda r_: (_sdist(r_), r_["type"], r_["name"].lower(), r_["file"], r_["line"]))

        # Apply limit
        results = results[:limit]

        if rescue:
            for r_ in results:
                r_["quality"] = "fuzzy"

        # Bloat diet: listings are the cheap navigation hop (detect -> symbols
        # -> detail); long docstrings live in detail. Keep the first 200 chars
        # of each docstring here and say exactly how much was cut, mirroring
        # the callers_omitted/callees_omitted convention.
        for r_ in results:
            doc = r_.get("docstring") or ""
            if len(doc) > _LISTING_DOCSTRING_CAP:
                head = doc[:_LISTING_DOCSTRING_CAP].rsplit(" ", 1)[0]
                r_["docstring"] = head + "…"
                r_["docstring_omitted"] = len(doc) - len(head)

        return results, rescue
    
