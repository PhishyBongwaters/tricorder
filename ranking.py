"""
Ranking mixin — DB-backed ranking + map (from core.py, DB-only).
"""
import os, sys, hashlib, threading
import networkx as nx
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from typing import List, Dict, Set, Tuple, Optional, Any
from utils import Tag, SymbolRecord
from report import FileReport
_COVERAGE_WARN_THRESHOLD = 60.0
from database import DBStore
from importance import filter_important_files
from render import render_tree, to_tree
from collections import defaultdict
from utils import Tag
from report import FileReport
_COVERAGE_WARN_THRESHOLD = 60.0

class RankingMixin:
    def _db_signature(self, included: List[str]) -> str:
        """Stat-based content signature from the walked files (meta.signature).

        Matches incremental (Goal 6) needs cheaply: (rel, size, mtime). Exact
        contents hashing is deferred; sizes+mtimes catch edited/added files.
        """
        parts = []
        for fname in sorted(included):
            try:
                st = os.stat(fname)
                parts.append(f"{self.get_rel_fname(fname)}:{st.st_size}:{int(st.st_mtime)}")
            except OSError:
                parts.append(self.get_rel_fname(fname))
        return hashlib.sha1("\n".join(parts).encode("utf-8")).hexdigest()[:16]

    def _get_ranked_tags_db(
        self,
        chat_fnames: List[str],
        other_fnames: List[str],
        mentioned_fnames: Set[str],
        mentioned_idents: Set[str],
    ) -> Tuple[List[Tuple[float, Tag]], FileReport]:
        """Flat-memory tree walk: each file's tags go to the DB, AST is dropped.

        Does NOT build the whole-repo defines/references/definitions dicts or
        the nx.MultiDiGraph the default path builds for PageRank — those are the
        memory blowup at scale (SPEC_db_map Goal 3). Rank order uses on-disk
        SQL power-iteration PageRank (Goal 4). Boosts/exclusion/sort match the
        default exactly. ponytail: single-shot full scan; incremental recompute
        is Goal 6.
        """
        def normalize_path(path):
            return str(Path(path).resolve())

        chat_fnames = [normalize_path(f) for f in chat_fnames]
        other_fnames = [normalize_path(f) for f in other_fnames]
        if mentioned_fnames is None:
            mentioned_fnames = set()
        if mentioned_idents is None:
            mentioned_idents = set()

        included: List[str] = []
        excluded: Dict[str, str] = {}
        chat_rel_fnames = set(self.get_rel_fname(f) for f in chat_fnames)
        all_fnames = list(set(chat_fnames + other_fnames))

        db = self._db_store
        
        # Check if DB already has valid data for the requested files
        # (Pre-scan case: db_path was provided and DB already populated)
        needed_rels = {self.get_rel_fname(f) for f in all_fnames}
        meta = db.get_meta()
        
        if meta and meta[0] == 1:  # schema_version == 1
            stored_root, stored_sig = meta[1], meta[2]
            stored_rels = db.stored_files()
            if stored_root == str(self.root):
                # Handles dirty-file incremental and resume of partial scans
                # (missing = not yet in DB). ponytail: one dirty set covers both.
                file_state = db.get_file_state()
                # Old DB without file_state: fall back to signature check (subset only)
                if not file_state:
                    if needed_rels.issubset(stored_rels):
                        current_sig = self._db_signature(all_fnames)
                        if current_sig == stored_sig:
                            for fname in all_fnames:
                                included.append(fname)
                            # Backfill file_state so future edits are incremental
                            for fname in all_fnames:
                                rel = self.get_rel_fname(fname)
                                try:
                                    st = os.stat(fname)
                                    db.set_file_state(rel, st.st_size, int(st.st_mtime))
                                except OSError:
                                    pass
                            db.commit()
                            self.output_handlers['info'](
                                f"Pre-scan DB hit: {len(needed_rels)} files covered, skipping parse")
                        else:
                            # Signature mismatch but no per-file state -> full rescan
                            db.reset()
                            for fname in all_fnames:
                                rel_fname = self.get_rel_fname(fname)
                                if not os.path.exists(fname):
                                    excluded[fname] = "File not found"
                                    self.output_handlers['warning'](
                                        f"Repo-map can't include {fname}: File not found")
                                    continue
                                included.append(fname)
                                tags = self.get_tags(fname, rel_fname)
                                if tags:
                                    db.insert_tags(
                                        (fname, rel_fname, t.line, t.name, t.kind) for t in tags)
                                try:
                                    st = os.stat(fname)
                                    db.set_file_state(rel_fname, st.st_size, int(st.st_mtime))
                                except OSError:
                                    pass
                            db.commit()
                            db.set_meta(str(self.root), self._db_signature(included))
                    else:  # superset + empty file_state (old partial DB) -> full rescan
                        db.reset()
                        for fname in all_fnames:
                            rel_fname = self.get_rel_fname(fname)
                            if not os.path.exists(fname):
                                excluded[fname] = "File not found"
                                self.output_handlers['warning'](
                                    f"Repo-map can't include {fname}: File not found")
                                continue
                            included.append(fname)
                            tags = self.get_tags(fname, rel_fname)
                            if tags:
                                db.insert_tags(
                                    (fname, rel_fname, t.line, t.name, t.kind) for t in tags)
                            try:
                                st = os.stat(fname)
                                db.set_file_state(rel_fname, st.st_size, int(st.st_mtime))
                            except OSError:
                                pass
                        db.commit()
                        db.set_meta(str(self.root), self._db_signature(included))
                else:  # file_state present -> dirty/missing diff covers resume
                    dirty_rels = set()
                    rel_to_fname = {self.get_rel_fname(f): f for f in all_fnames}
                    for rel in needed_rels:
                        fname = rel_to_fname[rel]
                        try:
                            st = os.stat(fname)
                            cur = (st.st_size, int(st.st_mtime))
                        except OSError:
                            # Deleted/missing -> treat as dirty (will be excluded)
                            dirty_rels.add(rel)
                            continue
                        stored = file_state.get(rel)
                        if stored is None or stored != cur:
                            dirty_rels.add(rel)
                    # Deleted files that were in DB but file gone (should not happen
                    # since needed_rels is subset, but guard anyway)
                    for fname in all_fnames:
                        if not os.path.exists(fname):
                            excluded[fname] = "File not found"
                            dirty_rels.discard(self.get_rel_fname(fname))

                    if not dirty_rels:
                        for fname in all_fnames:
                            if self.get_rel_fname(fname) in stored_rels:
                                included.append(fname)
                        self.output_handlers['info'](
                            f"Pre-scan DB hit: {len(needed_rels)} files covered, skipping parse")
                    else:
                        # Incremental: re-parse only dirty files
                        for fname in all_fnames:
                            rel = self.get_rel_fname(fname)
                            if rel in dirty_rels:
                                if not os.path.exists(fname):
                                    excluded[fname] = "File not found"
                                    self.output_handlers['warning'](
                                        f"Repo-map can't include {fname}: File not found")
                                    db.delete_tags_for_file(rel)
                                    continue
                                db.delete_tags_for_file(rel)
                                included.append(fname)
                                tags = self.get_tags(fname, rel)
                                if tags:
                                    db.insert_tags(
                                        (fname, rel, t.line, t.name, t.kind) for t in tags)
                                try:
                                    st = os.stat(fname)
                                    db.set_file_state(rel, st.st_size, int(st.st_mtime))
                                except OSError:
                                    pass
                            else:
                                # Cache hit — keep existing tags
                                included.append(fname)
                        db.commit()
                        db.set_meta(str(self.root), self._db_signature(included))
                        self.output_handlers['info'](
                            f"Incremental: {len(dirty_rels)} dirty, {len(needed_rels)-len(dirty_rels)} cache hits")
            else:
                # Fresh scan: never stack onto a previous run's rows in this file.
                db.reset()
                for fname in all_fnames:
                    rel_fname = self.get_rel_fname(fname)
                    if not os.path.exists(fname):
                        excluded[fname] = "File not found"
                        self.output_handlers['warning'](
                            f"Repo-map can't include {fname}: File not found")
                        continue
                    included.append(fname)
                    tags = self.get_tags(fname, rel_fname)
                    if tags:
                        # Persist now, drop the per-file tag list + AST immediately.
                        db.insert_tags(
                            (fname, rel_fname, t.line, t.name, t.kind) for t in tags)
                    try:
                        st = os.stat(fname)
                        db.set_file_state(rel_fname, st.st_size, int(st.st_mtime))
                    except OSError:
                        pass
                db.commit()
                db.set_meta(str(self.root), self._db_signature(included))
        else:
            # No meta or wrong schema — fresh scan
            db.reset()
            for fname in all_fnames:
                rel_fname = self.get_rel_fname(fname)
                if not os.path.exists(fname):
                    excluded[fname] = "File not found"
                    self.output_handlers['warning'](
                        f"Repo-map can't include {fname}: File not found")
                    continue
                included.append(fname)
                tags = self.get_tags(fname, rel_fname)
                if tags:
                    # Persist now, drop the per-file tag list + AST immediately.
                    db.insert_tags(
                        (fname, rel_fname, t.line, t.name, t.kind) for t in tags)
                try:
                    st = os.stat(fname)
                    db.set_file_state(rel_fname, st.st_size, int(st.st_mtime))
                except OSError:
                    pass
            db.commit()
            db.set_meta(str(self.root), self._db_signature(included))

        # Cross defs x refs into the refs edge table (on disk, not RAM).
        db.populate_refs()
        db.commit()

        total_definitions = db.count_tags("def")
        total_references = db.count_tags("ref")

        # Untagged files = included files with no def tag (matches default).
        tagged_rel_fnames = set(db.def_files())
        untagged = sorted(
            rel for fname in included
            for rel in [self.get_rel_fname(fname)]
            if rel not in tagged_rel_fnames
        )

        file_report = FileReport(
            excluded=excluded,
            definition_matches=total_definitions,
            reference_matches=total_references,
            total_files_considered=len(all_fnames),
            untagged_files=untagged
        )

        # Rank: on-disk PageRank via SQL power iteration (Goal 4).
        # Replaces the uniform 1.0 fallback — real PageRank now runs on-disk
        # without building an in-memory nx.MultiDiGraph.
        included_rels = {self.get_rel_fname(f) for f in included}
        chat_rel_set = chat_rel_fnames  # already a set of rel_fnames

        # Build personalization dict for the DB pagerank (same semantics as default).
        personalization = {}
        if chat_rel_set:
            for rel in chat_rel_set:
                personalization[rel] = 100.0

        # Get all included rel_files as nodes for PageRank.
        all_nodes = list(included_rels)
        ranks = db.pagerank(iter(all_nodes), alpha=0.85, personalization=personalization or None)

        ranked_tags: List[Tuple[float, Tag]] = []
        for fname, rel, line, name, _kind in db.def_rows():
            if rel not in included_rels:
                continue
            file_rank = ranks.get(rel, 0.0)

            # Exclude files with low Page Rank if exclude_unranked is True
            if self.exclude_unranked and file_rank <= 0.0001:
                continue

            boost = 1.0
            if name in mentioned_idents:
                boost *= 10.0
            if rel in mentioned_fnames:
                boost *= 5.0
            if rel in chat_rel_fnames:
                boost *= 20.0

            ranked_tags.append((file_rank * boost, Tag(rel, fname, line, name, "def")))

        ranked_tags.sort(key=lambda x: (-x[0], self.get_rel_fname(x[1].fname), x[1].line))
        return ranked_tags, file_report

    def get_ranked_tags(
        self,
        chat_fnames: List[str],
        other_fnames: List[str],
        mentioned_fnames: Optional[Set[str]] = None,
        mentioned_idents: Optional[Set[str]] = None
    ) -> Tuple[List[Tuple[float, Tag]], FileReport]:
        """Get ranked tags using PageRank algorithm with file report."""
        # Return empty list and empty report if no files
        if not chat_fnames and not other_fnames:
            return [], FileReport({}, 0, 0, 0, untagged_files=[])
        
        # SPEC_db_map Goal 3: flat-memory DB path (tags/refs persisted per
        # file, AST dropped immediately, no whole-repo dicts or nx graph).
        if self._db_active:
            return self._get_ranked_tags_db(
                chat_fnames, other_fnames, mentioned_fnames or set(),
                mentioned_idents or set())
            
        if mentioned_fnames is None:
            mentioned_fnames = set()
        if mentioned_idents is None:
            mentioned_idents = set()
        
        # Normalize paths to absolute
        def normalize_path(path):
            return str(Path(path).resolve())
        
        chat_fnames = [normalize_path(f) for f in chat_fnames]
        other_fnames = [normalize_path(f) for f in other_fnames]
        
        # Initialize file report
        included: List[str] = []
        excluded: Dict[str, str] = {}
        input_files: Dict[str, Dict] = {}
        total_definitions = 0
        total_references = 0
        
        # Collect all tags
        defines = defaultdict(set)
        references = defaultdict(set)
        definitions = defaultdict(set)
        
        personalization = {}
        chat_rel_fnames = set(self.get_rel_fname(f) for f in chat_fnames)
        
        all_fnames = list(set(chat_fnames + other_fnames))
        
        for fname in all_fnames:
            rel_fname = self.get_rel_fname(fname)
            
            if not os.path.exists(fname):
                reason = "File not found"
                excluded[fname] = reason
                self.output_handlers['warning'](f"Repo-map can't include {fname}: {reason}")
                continue
                
            included.append(fname)
            
            tags = self.get_tags(fname, rel_fname)
            
            for tag in tags:
                if tag.kind == "def":
                    defines[tag.name].add(rel_fname)
                    definitions[rel_fname].add(tag.name)
                    total_definitions += 1
                elif tag.kind == "ref":
                    references[tag.name].add(rel_fname)
                    total_references += 1
            
            # Set personalization for chat files
            if fname in chat_fnames:
                personalization[rel_fname] = 100.0
        
        # Build graph
        G = nx.MultiDiGraph()
        
        # Add nodes
        for fname in all_fnames:
            rel_fname = self.get_rel_fname(fname)
            G.add_node(rel_fname)
        
        # Add edges based on references
        for name, ref_fnames in references.items():
            def_fnames = defines.get(name, set())
            for ref_fname in ref_fnames:
                for def_fname in def_fnames:
                    if ref_fname != def_fname:
                        G.add_edge(ref_fname, def_fname, name=name)
        
        if not G.nodes():
            return [], FileReport({}, 0, 0, 0, untagged_files=[])
        
        # Run PageRank
        try:
            if personalization:
                ranks = nx.pagerank(G, personalization=personalization, alpha=0.85)
            else:
                ranks = {node: 1.0 for node in G.nodes()}
        except:
            # Fallback to uniform ranking
            ranks = {node: 1.0 for node in G.nodes()}
        
        # Update excluded dictionary with status information
        for fname in set(chat_fnames + other_fnames):
            if fname in excluded:
                # Add status prefix to existing exclusion reason
                excluded[fname] = f"[EXCLUDED] {excluded[fname]}"
            elif fname not in included:
                excluded[fname] = "[NOT PROCESSED] File not included in final processing"
        
        # Compute untagged files (included but no tree-sitter symbols)
        tagged_rel_fnames = set(definitions.keys())
        untagged = sorted(
            rel for fname in included
            for rel in [self.get_rel_fname(fname)]
            if rel not in tagged_rel_fnames
        )
        
        # Create file report
        file_report = FileReport(
            excluded=excluded,
            definition_matches=total_definitions,
            reference_matches=total_references,
            total_files_considered=len(all_fnames),
            untagged_files=untagged
        )
        
        # Collect and rank tags
        ranked_tags = []
        
        for fname in included:
            rel_fname = self.get_rel_fname(fname)
            file_rank = ranks.get(rel_fname, 0.0)

            # Exclude files with low Page Rank if exclude_unranked is True
            if self.exclude_unranked and file_rank <= 0.0001:  # Use a small threshold to exclude near-zero ranks
                continue
            
            tags = self.get_tags(fname, rel_fname)
            for tag in tags:
                if tag.kind == "def":
                    # Boost for mentioned identifiers
                    boost = 1.0
                    if tag.name in mentioned_idents:
                        boost *= 10.0
                    if rel_fname in mentioned_fnames:
                        boost *= 5.0
                    if rel_fname in chat_rel_fnames:
                        boost *= 20.0
                    
                    final_rank = file_rank * boost
                    ranked_tags.append((final_rank, tag))
        
        # Sort by rank (descending), then filename, line for determinism
        ranked_tags.sort(key=lambda x: (-x[0], self.get_rel_fname(x[1].fname), x[1].line))
        
        return ranked_tags, file_report
    
    # render_tree and to_tree are delegated to render.py (SPEC_db_map Goal 5a).
    # These thin wrappers keep the public API intact for tricorder.py,
    # tricorder_server.py, tests, and mem_probe.py.
    render_tree = render_tree
    to_tree = to_tree
    
    def to_mermaid(self, chat_fnames: List[str], other_fnames: List[str],
                   mentioned_fnames: Optional[Set[str]] = None,
                   mentioned_idents: Optional[Set[str]] = None,
                   ranked_tags: Optional[List[Tuple[float, Tag]]] = None,
                   max_nodes: Optional[int] = None) -> str:
        """Render the dependency graph as a Mermaid flowchart."""
        if ranked_tags is None:
            ranked_tags, _ = self.get_ranked_tags(
                chat_fnames, other_fnames, mentioned_fnames, mentioned_idents
            )
        if not ranked_tags:
            return ""

        # Rebuild the graph (same logic as get_ranked_tags)
        defines = defaultdict(set)
        references = defaultdict(set)
        personalization = {}
        chat_rel_fnames = set(self.get_rel_fname(f) for f in chat_fnames)
        all_fnames = list(set(chat_fnames + other_fnames))

        for fname in all_fnames:
            rel_fname = self.get_rel_fname(fname)
            if not os.path.exists(fname):
                continue
            tags = self.get_tags(fname, rel_fname)
            for tag in tags:
                if tag.kind == "def":
                    defines[tag.name].add(rel_fname)
                elif tag.kind == "ref":
                    references[tag.name].add(rel_fname)
            if fname in chat_fnames:
                personalization[rel_fname] = 100.0
        
        G = nx.MultiDiGraph()
        # Only include files that actually contribute symbols (appear in
        # defines or references). Files with zero tags (README.md, .png, etc.)
        # would otherwise clutter the graph as isolated nodes.
        tagged_fnames = set()
        for rel_fnames in references.values():
            tagged_fnames |= rel_fnames
        for def_fnames in defines.values():
            tagged_fnames |= def_fnames
        for fname in all_fnames:
            rel_fname = self.get_rel_fname(fname)
            if rel_fname in tagged_fnames or fname in chat_fnames:
                G.add_node(rel_fname)
        for name, ref_fnames in references.items():
            def_fnames = defines.get(name, set())
            for ref_fname in ref_fnames:
                for def_fname in def_fnames:
                    if ref_fname != def_fname:
                        G.add_edge(ref_fname, def_fname, name=name)
        
        # Rank nodes
        try:
            if personalization:
                ranks = nx.pagerank(G, personalization=personalization, alpha=0.85)
            else:
                ranks = {node: 1.0 for node in G.nodes()}
        except Exception:
            ranks = {node: 1.0 for node in G.nodes()}
        
        # Cap nodes by max_nodes if specified
        if max_nodes is not None and max_nodes < len(ranks):
            top_nodes = set(n for n, _ in sorted(ranks.items(), key=lambda x: x[1], reverse=True)[:max_nodes])
            # Filter graph to top nodes only
            G = nx.MultiDiGraph(G.subgraph(top_nodes))
        
        # Build Mermaid output
        lines = ["graph TD"]
        # Node definitions with styling — use relative paths for readability
        for node in sorted(G.nodes()):
            rank = ranks.get(node, 0.0)
            # Chat files get highlighted
            if node in chat_rel_fnames:
                lines.append(f'    {node.replace(".", "_").replace("/", "_")}["{node}"] :::chat')
            else:
                lines.append(f'    {node.replace(".", "_").replace("/", "_")}["{node}"]')
        
        # Edges
        for src, dst, data in G.edges(data=True):
            src_id = src.replace(".", "_").replace("/", "_")
            dst_id = dst.replace(".", "_").replace("/", "_")
            edge_name = data.get("name", "")
            lines.append(f'    {src_id} -->|{edge_name}| {dst_id}')
        
        # Styling
        lines.append("")
        lines.append("    classDef chat fill:#f9f,stroke:#333,stroke-width:2px")
        
        return "\n".join(lines)
    
    def get_ranked_tags_map(
        self,
        chat_fnames: List[str],
        other_fnames: List[str],
        max_map_tokens: int,
        mentioned_fnames: Optional[Set[str]] = None,
        mentioned_idents: Optional[Set[str]] = None,
        force_refresh: bool = False,
        output_writer=None,
    ) -> Optional[str]:
        """Get the ranked tags map with persistent disk caching."""
        # Streaming bypasses cache (output goes to writer, not returned)
        if output_writer is not None or force_refresh:
            return self.get_ranked_tags_map_uncached(
                chat_fnames, other_fnames, max_map_tokens,
                mentioned_fnames, mentioned_idents, output_writer=output_writer
            )

        cache_key = (
            tuple(sorted(chat_fnames)),
            tuple(sorted(other_fnames)),
            max_map_tokens,
            tuple(sorted(mentioned_fnames or [])),
            tuple(sorted(mentioned_idents or [])),
            self.full_map,
        )
        
        if not force_refresh:
            with self._tags_cache_lock:
                try:
                    cached = self.TAGS_CACHE.get(str(cache_key))
                    if cached is not None:
                        try:
                            with open(os.path.join(self._cache_dir(), "hits.log"), "a") as _hf:
                                _hf.write(f"hit\tranked_tags_map\n")
                        except Exception:
                            pass
                        return cached
                except Exception:
                    pass
        
        result = self.get_ranked_tags_map_uncached(
            chat_fnames, other_fnames, max_map_tokens,
            mentioned_fnames, mentioned_idents
        )
        
        if not force_refresh:
            with self._tags_cache_lock:
                try:
                    self.TAGS_CACHE[str(cache_key)] = result
                except Exception:
                    pass
        return result
    
    def get_ranked_tags_map_uncached(
        self,
        chat_fnames: List[str],
        other_fnames: List[str],
        max_map_tokens: int,
        mentioned_fnames: Optional[Set[str]] = None,
        mentioned_idents: Optional[Set[str]] = None,
        output_writer=None,
    ) -> Tuple[Optional[str], FileReport]:
        """Generate the ranked tags map without caching."""
        ranked_tags, file_report = self.get_ranked_tags(
            chat_fnames, other_fnames, mentioned_fnames, mentioned_idents
        )
        
        if not ranked_tags:
            return None, file_report
        
        # Filter important files
        important_files = filter_important_files(
            [self.get_rel_fname(f) for f in other_fnames]
        )
        
        # Binary search to find the right number of tags
        chat_rel_fnames = set(self.get_rel_fname(f) for f in chat_fnames)
        
        # Full map: skip token-budget binary search, emit all ranked tags
        if self.full_map:
            if output_writer is not None:
                self.to_tree(ranked_tags, chat_rel_fnames, important_files, writer=output_writer)
                best_tree = None
            else:
                best_tree = self.to_tree(ranked_tags, chat_rel_fnames, important_files)
            best_num = len(ranked_tags)
            file_report.total_files_considered = len(other_fnames)
            return best_tree, file_report
        
        def try_tags(num_tags: int) -> Tuple[Optional[str], int]:
            if num_tags <= 0:
                return None, 0
            
            selected_tags = ranked_tags[:num_tags]
            # Binary search measures tag cost only — untagged files are
            # metadata added once to the final output, not per-iteration.
            tree_output = self.to_tree(selected_tags, chat_rel_fnames, [])
            
            if not tree_output:
                return None, 0
            
            tokens = self.token_count(tree_output)
            return tree_output, tokens
        
        # Binary search for optimal number of tags
        left, right = 0, len(ranked_tags)
        best_tree = None
        best_num = 0
        # Fallback: track the smallest tree even if it exceeds budget
        fallback_tree = None
        fallback_num = 0
        fallback_tokens = float('inf')

        while left <= right:
            mid = (left + right) // 2
            tree_output, tokens = try_tags(mid)

            if tree_output and tokens <= max_map_tokens:
                best_tree = tree_output
                best_num = mid
                left = mid + 1
            else:
                # Track fallback: smallest tree that exceeds budget
                if tree_output and tokens < fallback_tokens:
                    fallback_tree = tree_output
                    fallback_num = mid
                    fallback_tokens = tokens
                right = mid - 1

        # Fallback: if no valid tree found, use the smallest one that exceeded budget
        if best_tree is None and fallback_tree is not None:
            best_tree = fallback_tree
            best_num = fallback_num
            self.output_handlers['warning'](
                f"Map exceeds token budget ({fallback_tokens} > {max_map_tokens} tokens) "
                f"with {fallback_num} tag(s). Consider increasing --map-tokens."
            )

        # Coverage: distinct source files that actually made it into the map,
        # vs. how many the scanner considered. Low coverage means the token
        # budget rendered a thin slice --- an agent must NOT mistake it for
        # the whole repo. Emit a warning so "small map" stays honest (issue
        # #18). Threshold is a knob (_COVERAGE_WARN_THRESHOLD).
        tagged_files = set(self.get_rel_fname(t[1].fname) for t in ranked_tags[:best_num])
        covered = len(tagged_files)
        total_considered = file_report.total_files_considered
        coverage_pct = round(covered / total_considered * 100, 1) if total_considered else 100.0
        self.last_coverage_pct = coverage_pct
        if coverage_pct < _COVERAGE_WARN_THRESHOLD:
            self.output_handlers['warning'](
                f"Low map coverage: {covered}/{total_considered} source files ({coverage_pct}%). "
                f"The answer to a task may live in an uncovered file — raise --map-tokens "
                f"or drill in with detect/symbols/query."
            )
        
        # Add untagged files section to final output (not counted in token budget)
        if best_tree and file_report.untagged_files and not self.exclude_untagged and self.context_lines == 0:
            other_lines = []
            for uf in file_report.untagged_files:
                abs_path = str(self.root / uf)
                code = self.read_text_func_internal(abs_path)
                if code:
                    lc = len(code.splitlines())
                    other_lines.append(f"{uf} ({lc} lines)")
                else:
                    other_lines.append(uf)
            if other_lines:
                best_tree = best_tree + "\n\nOther files:\n" + "\n".join(other_lines)
        
        # Attach coverage_pct to file_report so MCP/CLI can surface it (issue #18)
        file_report.coverage_pct = coverage_pct
        
        return best_tree, file_report
    
    def get_repo_map(
        self,
        chat_files: Optional[List[str]] = None,
        other_files: Optional[List[str]] = None,
        mentioned_fnames: Optional[Set[str]] = None,
        mentioned_idents: Optional[Set[str]] = None,
        force_refresh: bool = False,
        output_writer=None,
    ) -> Tuple[Optional[str], FileReport]:
        """Generate the repository map with file report.

        When output_writer is provided (streaming mode), the map content
        is written to it and None is returned as the string.
        """
        chat_files = chat_files or []
        other_files = other_files or []

        # Create empty report for error cases
        empty_report = FileReport({}, 0, 0, 0, untagged_files=[], coverage_pct=100.0)

        if self.max_map_tokens <= 0 or not other_files:
            return None, empty_report

        # Adjust max_map_tokens if no chat files
        max_map_tokens = self.max_map_tokens
        if not chat_files and self.max_context_window:
            padding = 1024
            available = self.max_context_window - padding
            max_map_tokens = min(
                max_map_tokens * self.map_mul_no_files,
                available
            )

        try:
            # get_ranked_tags_map returns (map_string, file_report)
            map_string, file_report = self.get_ranked_tags_map(
                chat_files, other_files, max_map_tokens,
                mentioned_fnames, mentioned_idents, force_refresh,
                output_writer=output_writer
            )
        except RecursionError:
            self.output_handlers['error']("Disabling repo map, git repo too large?")
            self.max_map_tokens = 0
            return None, FileReport({}, 0, 0, 0, untagged_files=[], coverage_pct=100.0)  # Ensure consistent return type

        if map_string is None:
            return None, file_report

        if self.verbose:
            tokens = self.token_count(map_string)
            self.output_handlers['info'](f"Repo-map: {tokens / 1024:.1f} k-tokens")

        # Format final output
        other = "other " if chat_files else ""

        if self.repo_content_prefix:
            repo_content = self.repo_content_prefix.format(other=other)
        else:
            repo_content = ""

        repo_content += map_string

        return repo_content, file_report
