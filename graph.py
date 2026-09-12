"""
Graph mixin — cross-file index, call graph, detail (from core.py).
"""
import os, sys, hashlib, fnmatch, threading
import networkx as nx
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from typing import List, Dict, Tuple, Optional, Any
from utils import SymbolRecord, Tag, discover_src_files, repo_budget, count_tokens, detect_lang, read_text
import json as _json
from scm import get_scm_fname
from collections import defaultdict
from cache import CACHE_VERSION

class GraphMixin:
    def _discover_files(self) -> List[str]:
        """Discover source files under self.root. Uses shared skip logic."""
        return discover_src_files(str(self.root), use_gitignore=True, exclude_globs=self.exclude_globs)

    _import_index_cache: Dict[str, Dict] = None  # type: ignore[assignment]

    _CROSS_REF_DISK_KEY = "__cross_ref_index_v1__"

    def _cross_ref_fingerprint(self) -> str:
        """Fingerprint of every discovered file's (rel path, mtime).

        One stat per file, no tree-sitter parse. Any add/edit/delete changes
        the fingerprint, so a matching fingerprint means the persisted
        cross-file/import indexes are still valid for THIS repo snapshot.
        """
        entries = []
        for fpath in self._discover_files():
            try:
                m = os.path.getmtime(fpath)
            except OSError:
                continue
            entries.append((self.get_rel_fname(fpath).replace("\\", "/"), m))
        entries.sort()
        # CACHE_VERSION: index format/logic changes must invalidate old
        # bundles (a matching fingerprint must mean valid for THIS code too).
        return hashlib.sha256(
            (repr(entries) + f"|cv{CACHE_VERSION}").encode("utf-8")).hexdigest()

    def _load_cross_ref_disk(self) -> bool:
        """Restore the import+cross-file indexes from diskcache if valid.

        Also restores self._file_refs_index (detail uses it for in-file
        callers/callees). Returns True on a valid hit. Both TAGS_CACHE types
        (diskcache.Cache and the plain-dict fallback) expose .get/.set.
        """
        try:
            bundle = self.TAGS_CACHE.get(self._CROSS_REF_DISK_KEY)
            if not bundle:
                return False
            if bundle.get("fingerprint") != self._cross_ref_fingerprint():
                return False
            self._import_index_cache = bundle["import_index"]
            self._cross_file_index_cache = bundle["cross_file_idx"]
            self._file_refs_index = bundle["file_refs_index"]
            return True
        except Exception:
            return False

    def _save_cross_ref_disk(self):
        """Persist the import+cross-file indexes + file_refs to diskcache.

        Computes the fingerprint lazily (one stat pass). Failure is harmless —
        next call rebuilds in memory. Only diskcache.Cache persists; the
        plain-dict fallback stays in-memory.
        """
        try:
            if not hasattr(self.TAGS_CACHE, "set"):
                return  # in-memory fallback — nothing durable to write to
            self.TAGS_CACHE.set(self._CROSS_REF_DISK_KEY, {
                "fingerprint": self._cross_ref_fingerprint(),
                "import_index": self._import_index_cache,
                "cross_file_idx": self._cross_file_index_cache,
                "file_refs_index": getattr(self, "_file_refs_index", {}),
            })
        except Exception:
            pass  # evicted/disk error — rebuild next call

    def _build_import_index(self) -> Dict[str, Dict]:

        """Build import bindings and name resolver for all source files.

        Returns a dict with:
          - 'resolver': NameResolver instance
          - 'file_imports': {file_path: [ImportBinding, ...]}
        ponytail: one pass over all files, cached on the instance — Tricorder is
        per-call in the MCP server, so no cross-project stale-cache risk.
        """
        # Fast path: cache hit (no lock needed for read)
        if self._import_index_cache is not None:
            return self._import_index_cache

        # Disk cache: restore the whole import+cross-file bundle if the repo
        # snapshot is unchanged. Avoids re-parsing imports on every detail().
        if self._load_cross_ref_disk():
            return self._import_index_cache

        # Lock for write - double-checked locking
        with self._import_index_lock:
            # Double-check after acquiring lock
            if self._import_index_cache is not None:
                return self._import_index_cache
            from import_parser import parse_imports
            from name_resolver import NameResolver

            resolver = NameResolver()
            file_imports = {}

            for fpath in self._discover_files():
                if not os.path.isfile(fpath):
                    continue
                try:
                    from grep_ast.tsl import get_parser
                except ImportError:
                    continue

                lang = detect_lang(fpath)
                if not lang:
                    continue

                try:
                    parser = get_parser(lang)
                except Exception:
                    continue

                code = self.read_text_func_internal(fpath)
                if not code or not code.strip():
                    continue

                try:
                    bindings = parse_imports(fpath, lang, parser, bytes(code, "utf-8"))
                    if bindings:
                        file_imports[fpath] = bindings
                        resolver.add_file(fpath, bindings)
                except Exception:
                    pass

            result = {'resolver': resolver, 'file_imports': file_imports}
            self._import_index_cache = result
            return result

    def _build_cross_file_index(self) -> Tuple[Dict[str, List[Tuple[str, int]]], Dict[str, List[Tuple[str, int]]]]:
        """Build cross-file definition and reference indexes.

        Returns (defs, refs) where each maps symbol_name -> [(file, line)].
        ponytail: one pass over all files, O(n) total.
        Uses import tracking to resolve qualified names where possible.
        """
        # Fast path: check if we have a cached cross-file index
        if hasattr(self, '_cross_file_index_cache') and self._cross_file_index_cache is not None:
            return self._cross_file_index_cache

        # Disk cache: restore the whole bundle if the repo snapshot is unchanged.
        if self._load_cross_ref_disk():
            return self._cross_file_index_cache

        # Lock for write - double-checked locking
        with self._cross_file_index_lock:
            # Double-check after acquiring lock
            if hasattr(self, '_cross_file_index_cache') and self._cross_file_index_cache is not None:
                return self._cross_file_index_cache
            
            defs: Dict[str, List[Tuple[str, int]]] = defaultdict(list)
            refs: Dict[str, List[Tuple[str, int]]] = defaultdict(list)
            file_refs_index: Dict[str, List[dict]] = {}

            # Build import index for qualified name resolution
            import_data = self._build_import_index()
            resolver = import_data['resolver']
            file_imports = import_data['file_imports']

            for fpath in self._discover_files():
                if not os.path.isfile(fpath):
                    continue
                rel = self.get_rel_fname(fpath)

                # Definitions
                for sym in self.get_symbols(fpath, rel):
                    defs[sym.name].append((fpath, sym.line))

                # References — resolve qualified names via import tracking
                file_refs = self.get_all_references(fpath, rel)
                file_refs_index[fpath.replace("\\", "/")] = file_refs
                for ref in file_refs:
                    bare_name = ref["name"]
                    # Try to resolve to a qualified name
                    resolution = resolver.resolve(bare_name, fpath)
                    if resolution.confidence > 0:
                        # Use qualified name for the reference
                        resolved_name = resolution.qualified_name
                        # Only use qualified name if it differs from bare name
                        # (avoids polluting the index with redundant entries)
                        if resolved_name != bare_name:
                            refs[resolved_name].append((fpath, ref["line"]))
                        # Always index the bare name too (for backward compat)
                        refs[bare_name].append((fpath, ref["line"]))
                    else:
                        # No import mapping — use bare name
                        refs[bare_name].append((fpath, ref["line"]))

            # Stop-names (mirror populate_refs' >50-file guard): names
            # defined in >50 files are unresolvable by name. Drop their ref
            # entries so detail/query agree with the DB instead of showing
            # fake precision the ranker never had. Defs stay (tags are facts).
            for _n in [n for n, ds in defs.items()
                       if len({f for f, _ in ds}) > 50]:
                refs.pop(_n, None)
            result = (dict(defs), dict(refs))
            self._cross_file_index_cache = result
            self._file_refs_index = file_refs_index
            # Persist the full import+cross-file bundle so a fresh process
            # (every MCP call) restores it without re-parsing the repo.
            self._save_cross_ref_disk()
            return result

    def build_call_graph(self, file_paths: List[str]) -> Dict[str, Dict]:
        """Build a per-file call graph from reference captures.

        Returns {abs_path: {"definitions": {name: line}, "references": [{line, name, type}]}}.
        ponytail: O(n) per file — one tree-sitter parse, one pass over captures.
        """
        graph = {}
        for fpath in file_paths:
            rel = self.get_rel_fname(fpath)
            if not os.path.isfile(fpath):
                continue
            # Get definitions (name -> line)
            defs = {}
            symbols = self.get_symbols(fpath, rel)
            for sym in symbols:
                defs[sym.name] = sym.line

            # Get references
            refs = self.get_all_references(fpath, rel)

            graph[fpath] = {
                "definitions": defs,
                "references": refs,
            }
        return graph

    def query_graph(self, parsed_query: 'ParsedQuery', token_limit: int = 2048) -> Dict[str, Any]:
        """Execute a parsed graph query and return subgraph.

        Args:
            parsed_query: ParsedQuery object from parse_query_dsl
            token_limit: Maximum tokens for response (used for truncation hint)

        Returns:
            dict with keys: nodes, edges, token_estimate, full_repo_estimate,
            savings_pct, tier_hint (if truncated), stats
        """
        from utils import count_tokens, ParsedQuery, TraversalStep, QueryModifiers

        if not parsed_query.steps:
            return {"nodes": [], "edges": [], "token_estimate": 0, "full_repo_estimate": 0,
                    "savings_pct": 0.0, "stats": {"nodes_visited": 0, "edges_traversed": 0}}

        # Build full cross-file index (definitions and references)
        defs, refs = self._build_cross_file_index()

        # Build per-file call graphs for in-file traversal
        all_files = self._discover_files()
        file_graphs = self.build_call_graph(all_files)

        # Helper: filter file by exclude/include globs
        def file_allowed(filepath: str, mods: QueryModifiers) -> bool:
            if not mods.exclude_globs and not mods.include_globs:
                return True
            rel = self.get_rel_fname(filepath).replace('\\', '/')
            if mods.exclude_globs:
                if any(fnmatch.fnmatch(rel, pat) for pat in mods.exclude_globs):
                    return False
            if mods.include_globs:
                if not any(fnmatch.fnmatch(rel, pat) for pat in mods.include_globs):
                    return False
            return True

        # Helper: get symbol type for filtering
        def get_symbol_type(filepath: str, symbol_name: str) -> Optional[str]:
            rel = self.get_rel_fname(filepath)
            symbols = self.get_symbols(filepath, rel)
            for sym in symbols:
                sym_name = sym.name
                if '::' in sym_name:
                    sym_name = sym_name.split('::', 1)[-1]
                if '(' in sym_name:
                    sym_name = sym_name.split('(', 1)[0]
                elif sym_name.endswith('()'):
                    sym_name = sym_name[:-2]
                if sym_name == symbol_name:
                    return sym.type
            return None

        # Helper: find containing symbol at a given line in a file
        def find_containing_symbol(filepath: str, line: int) -> Optional[Dict]:
            """Find the function/class that contains the given line."""
            rel = self.get_rel_fname(filepath)
            symbols = self.get_symbols(filepath, rel)
            best_match = None
            for sym in symbols:
                sym_end = sym.end_line if sym.end_line and sym.end_line > sym.line else sym.line + 10
                if sym.line <= line <= sym_end:
                    span = sym_end - sym.line
                    if best_match is None or span < (best_match["end_line"] - best_match["line"]):
                        best_match = {"name": sym.name, "type": sym.type, "line": sym.line, "end_line": sym_end}
            return best_match

        # Helper: get all symbols in a file for quick lookup
        def get_file_symbols(filepath: str) -> List[Dict]:
            rel = self.get_rel_fname(filepath)
            symbols = self.get_symbols(filepath, rel)
            return [{"name": s.name, "type": s.type, "line": s.line, "end_line": s.end_line} for s in symbols]

        # Track visited nodes and edges
        nodes = []  # List of {name, file, line, type}
        edges = []  # List of {from, to, from_file, to_file, from_line, to_line, type}
        seen_nodes = set()  # (name, file, line)
        total_nodes_found = 0

        # Start with the first step's target
        current_targets = []  # List of (name, file, line)

        for step_idx, step in enumerate(parsed_query.steps):
            kind = step.kind
            target_name = step.target
            mods = step.modifiers

            if step_idx == 0:
                # First step: find all definitions matching target_name
                for def_file, def_line in defs.get(target_name, []):
                    if not file_allowed(def_file, mods):
                        continue
                    if mods.symbol_type:
                        sym_type = get_symbol_type(def_file, target_name)
                        if sym_type != mods.symbol_type:
                            continue
                    current_targets.append((target_name, def_file, def_line))
            else:
                # Subsequent steps: current_targets already populated from previous step
                pass

            # BFS traversal for this step
            step_nodes = []
            step_edges = []
            visited = set()  # (name, file, line)
            queue = [(name, file, line, 0) for name, file, line in current_targets]  # (name, file, line, depth)

            while queue and len(step_nodes) < mods.limit:
                name, file, line, depth = queue.pop(0)
                if depth > mods.depth:
                    continue
                key = (name, file, line)
                if key in visited:
                    continue
                visited.add(key)

                # Add node if not already in global nodes
                global_key = (name, file, line)
                if global_key not in seen_nodes:
                    sym_type = get_symbol_type(file, name)
                    node = {"name": name, "file": file, "line": line, "type": sym_type or "unknown"}
                    step_nodes.append(node)
                    nodes.append(node)
                    seen_nodes.add(global_key)
                    total_nodes_found += 1

                # Get neighbors based on traversal kind
                neighbors = []  # List of (neighbor_name, neighbor_file, neighbor_line, edge_type)

                if kind == "callers":
                    # Find callers: references TO this symbol in ANY file
                    for ref_file, ref_line in refs.get(name, []):
                        if not file_allowed(ref_file, mods):
                            continue
                        if ref_file == file and ref_line == line:
                            continue  # Skip self-reference
                        if mods.symbol_type:
                            sym_type = get_symbol_type(ref_file, name)
                            if sym_type != mods.symbol_type:
                                continue
                        # Find the caller (containing symbol) at this reference location
                        caller = find_containing_symbol(ref_file, ref_line)
                        if caller:
                            neighbors.append((caller["name"], ref_file, caller["line"], "calls"))
                        else:
                            # Fallback: use the reference name as caller
                            neighbors.append((name, ref_file, ref_line, "calls"))

                elif kind == "callees":
                    # Find callees: symbols that THIS symbol calls (references FROM this symbol's body)
                    # Use the per-file call graph
                    file_graph = file_graphs.get(file, {"definitions": {}, "references": []})
                    file_refs = file_graph.get("references", [])
                    # Find references made BY this symbol (at or near its line)
                    file_symbols = get_file_symbols(file)
                    containing = None
                    for sym in file_symbols:
                        if sym["line"] <= line <= sym["end_line"]:
                            containing = sym
                            break
                    if containing:
                        # Find references in this containing symbol's body
                        for ref in file_refs:
                            if containing["line"] <= ref["line"] <= containing["end_line"]:
                                callee_name = ref["name"]
                                callee_base = callee_name.split('::', 1)[-1] if '::' in callee_name else callee_name
                                name_base = name.split('::', 1)[-1] if '::' in name else name
                                if callee_base == name_base:
                                    continue  # Skip self-reference
                                # Find definitions of this callee
                                for def_file, def_line in defs.get(callee_name, []):
                                    if not file_allowed(def_file, mods):
                                        continue
                                    if mods.symbol_type:
                                        sym_type = get_symbol_type(def_file, callee_name)
                                        if sym_type != mods.symbol_type:
                                            continue
                                    neighbors.append((callee_name, def_file, def_line, "calls"))

                elif kind == "refs":
                    # Find all references TO this symbol
                    for ref_file, ref_line in refs.get(name, []):
                        if not file_allowed(ref_file, mods):
                            continue
                        if ref_file == file and ref_line == line:
                            continue
                        if mods.symbol_type:
                            sym_type = get_symbol_type(ref_file, name)
                            if sym_type != mods.symbol_type:
                                continue
                        neighbors.append((name, ref_file, ref_line, "refers"))

                elif kind == "defs":
                    # Find all definitions OF this symbol
                    for def_file, def_line in defs.get(name, []):
                        if not file_allowed(def_file, mods):
                            continue
                        if def_file == file and def_line == line:
                            continue
                        if mods.symbol_type:
                            sym_type = get_symbol_type(def_file, name)
                            if sym_type != mods.symbol_type:
                                continue
                        neighbors.append((name, def_file, def_line, "defines"))

                # Add neighbors to queue and edges
                for n_name, n_file, n_line, edge_type in neighbors:
                    n_key = (n_name, n_file, n_line)
                    if n_key not in visited and n_key not in seen_nodes:
                        queue.append((n_name, n_file, n_line, depth + 1))
                    if len(step_edges) < mods.limit * 2:
                        # Edge: from current node TO neighbor
                        # For callers: caller calls callee (current), so edge is caller -> callee
                        # For callees: current calls callee, so edge is current -> callee
                        if kind in ("callers", "refs", "defs"):
                            # For callers/refs/defs, we're traversing TO the current node
                            # So the neighbor is the "from" and current is "to"
                            step_edges.append({
                                "from": n_name, "to": name,
                                "from_file": n_file, "to_file": file,
                                "from_line": n_line, "to_line": line,
                                "type": edge_type
                            })
                        else:
                            # For callees, we're traversing FROM current TO neighbor
                            step_edges.append({
                                "from": name, "to": n_name,
                                "from_file": file, "to_file": n_file,
                                "from_line": line, "to_line": n_line,
                                "type": edge_type
                            })

            # Add step edges to global edges
            edges.extend(step_edges)

            # For next step, use nodes found in this step as starting points
            if step_idx < len(parsed_query.steps) - 1:
                current_targets = [(n["name"], n["file"], n["line"]) for n in step_nodes]

        # Build response
        import json as _json
        resp_dict = {"nodes": nodes, "edges": edges}
        token_est = count_tokens(_json.dumps(resp_dict))

        budget = repo_budget(self.root, 0)
        full_repo = budget.get("full_repo_estimate", 0)

        savings = 0.0
        if full_repo:
            savings = round(max(0.0, 1 - token_est / full_repo) * 100, 1)

        tier_hint = None
        if token_est > token_limit:
            tier_hint = f"Response truncated: {token_est} tokens > limit {token_limit}. Consider increasing token_limit or reducing depth/limit."

        return {
            "nodes": nodes[:token_limit // 50],
            "edges": edges[:token_limit // 30],
            "token_estimate": token_est,
            "full_repo_estimate": full_repo,
            "savings_pct": savings,
            "tier_hint": tier_hint,
            "stats": {"nodes_visited": total_nodes_found, "edges_traversed": len(edges)}
        }


    def get_symbol_detail(self, file_path: str, symbol_name: str, line: int = 0) -> Optional[SymbolRecord]:
        """Get full details for a single symbol by file + name + optional line.

        Returns a SymbolRecord with body populated (first 500 chars of the
        symbol's code block). Callers/callees are populated from:
          - In-file: tree-sitter reference captures within the same file
          - Cross-file: full-repo scan matching references to definitions

        Returns None if symbol not found.
        """
        if not os.path.isfile(file_path):
            return None

        # Try to find the symbol via get_symbols first
        rel_path = self.get_rel_fname(file_path)
        symbols = self.get_symbols(file_path, rel_path)

        target = None
        # Exact (case-sensitive) match first, then a fuzzy fallback that mirrors
        # detect/symbols' substring matching so a symbol detect found easily
        # isn't "not found" to detail over a case/scope/paren/template mismatch.
        # TC-011: this is the root of the "not found" retry loop — detail was
        # brittle where the explore tools are fuzzy.
        def _base(name: str) -> str:
            if '::' in name:
                name = name.split('::', 1)[-1]
            if '(' in name:
                name = name.split('(', 1)[0]
            elif name.endswith('()'):
                name = name[:-2]
            return name
        symbol_l = symbol_name.lower()
        for sym in symbols:
            sym_name = _base(sym.name)
            if sym_name == symbol_name:
                if line == 0 or sym.line == line:
                    target = sym
                    break
        if target is None:
            # fuzzy: case-insensitive + substring (mirror detect/symbols)
            for sym in symbols:
                sym_name = _base(sym.name).lower()
                if sym_name == symbol_l or symbol_l in sym_name or sym_name in symbol_l:
                    if line == 0 or sym.line == line:
                        target = sym
                        break
        if target is None:
            return None

        # Extract body: mtime-cached file text, truncate to 500 chars
        code = self.get_file_text(file_path)
        if not code:
            target.body = ""
            return target

        lines = code.splitlines()
        start = max(0, target.line - 1)
        end = min(len(lines), target.end_line)
        body_lines = lines[start:end]
        body_text = "\n".join(body_lines)
        target.body = body_text[:500]

        # Build in-file call graph for callers/callees from the single
        # cross-file index pass (issue #15: avoid re-parsing the file).
        self._build_cross_file_index()  # populates self._file_refs_index
        _np = file_path.replace("\\", "/")
        file_refs = self._file_refs_index.get(_np) or []

        # In-file callers: lines in this file that reference this symbol's name
        # ponytail: function-scope guard — only refs within the symbol's body
        callers = []
        for ref in file_refs:
            if ref["name"] == symbol_name:
                if ref["line"] >= target.line and ref["line"] <= target.end_line:
                    callers.append({"file": file_path, "line": ref["line"], "cross_file": False})

        # In-file callees: unique symbols called WITHIN this symbol's body
        # ponytail: function-scope guard — excludes refs in sibling functions
        callees = []
        seen = set()
        for ref in file_refs:
            if ref["name"] == symbol_name:
                continue
            if ref["name"] in seen:
                continue
            if ref["line"] < target.line or ref["line"] > target.end_line:
                continue
            seen.add(ref["name"])
            callees.append({"name": ref["name"], "file": file_path, "line": ref["line"], "cross_file": False})

        # Cross-file callers: references to this symbol in OTHER files
        # ponytail: normalize path separators — cross-file index uses os.path
        # (backslashes on Windows) but file_path may have forward slashes.
        defs, refs = self._build_cross_file_index()
        for ref_file, ref_line in refs.get(symbol_name, []):
            if ref_file.replace("\\", "/") != _np:
                callers.append({"file": ref_file, "line": ref_line, "cross_file": True})

        # Cross-file callees: symbols defined in OTHER files that this file references
        # Uses import tracking to resolve qualified names
        import_data = self._build_import_index()
        resolver = import_data['resolver']

        # ponytail: function-scope guard for cross-file callees too
        for ref in file_refs:
            ref_name = ref["name"]
            if ref_name == symbol_name:
                continue
            # Exclude refs outside this function's body
            if ref["line"] < target.line or ref["line"] > target.end_line:
                continue
            # Resolve to qualified name if possible
            resolution = resolver.resolve(ref_name, file_path)
            search_name = resolution.qualified_name if resolution.confidence > 0 else ref_name
            # Check if the resolved name is defined somewhere else
            for def_file, def_line in defs.get(search_name, []):
                if def_file.replace("\\", "/") != _np:
                    entry = {"name": search_name, "file": def_file, "line": def_line, "cross_file": True}
                    if entry not in callees:
                        callees.append(entry)
                    break  # Only add the first definition match

        target.callers = callers
        target.callees = callees

        # Stop-name note: no cross-file callers may mean "too common to
        # resolve", not "uncalled". The DB persists the skipped set.
        try:
            _db = getattr(self, "_db_store", None)
            if (_db is not None and
                    not any(c.get("cross_file") for c in callers) and
                    _db.is_stop_name(_base(symbol_name))):
                target.stop_note = (
                    f"'{symbol_name}' is defined in >50 files: too common "
                    "to resolve callers by name.")
        except Exception:
            pass

        return target

