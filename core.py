"""
Tricorder class for generating repository maps.
"""

import os
import sys
import fnmatch
from pathlib import Path
from collections import namedtuple, defaultdict
from typing import List, Dict, Set, Optional, Tuple, Callable, Any, Union
import shutil
import sqlite3
from dataclasses import dataclass
import diskcache
import networkx as nx
from grep_ast import TreeContext
from utils import count_tokens, read_text, Tag, SymbolRecord, discover_src_files, detect_lang, ParsedQuery, repo_budget
from scm import get_scm_fname
from importance import filter_important_files


class TricorderError(Exception):
    """Base exception for Tricorder errors."""
    pass


class GrepAstNotAvailableError(TricorderError):
    """Raised when grep-ast is not available."""
    pass


@dataclass
class FileReport:
    excluded: Dict[str, str]        # File -> exclusion reason with status
    definition_matches: int         # Total definition tags
    reference_matches: int          # Total reference tags
    total_files_considered: int     # Total files provided as input
    untagged_files: List[str] = None # Files with no tree-sitter symbols



# Constants
CACHE_VERSION = 1

TAGS_CACHE_DIR = f".repomap.tags.cache.v{CACHE_VERSION}"
SQLITE_ERRORS = (sqlite3.OperationalError, sqlite3.DatabaseError)



class Tricorder:
    """Main class for generating repository maps."""
    
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
        exclude_globs: Optional[List[str]] = None
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
        
        # Load persistent tags cache
        self.load_tags_cache()
    
    def load_tags_cache(self):
        """Load the persistent tags cache."""
        cache_dir = self.root / TAGS_CACHE_DIR
        try:
            self.TAGS_CACHE = diskcache.Cache(str(cache_dir))
        except Exception as e:
            # Fall back to in-memory cache — common on Windows with
            # read-only cache files from previous runs.
            self.output_handlers['warning'](
                f"Failed to initialize diskcache at {cache_dir}: {e}. "
                f"Falling back to in-memory cache (not persistent)."
            )
            self.TAGS_CACHE = {}
    
    def _make_writable(self, path: Path):
        """Try to make a file/directory writable on Windows."""
        try:
            import stat
            path.chmod(path.stat().st_mode | stat.S_IWRITE)
        except Exception:
            pass
    
    def tags_cache_error(self):
        """Handle tags cache errors."""
        try:
            cache_dir = self.root / TAGS_CACHE_DIR
            if cache_dir.exists():
                # Make all files writable before removing
                for root, dirs, files in os.walk(cache_dir, topdown=False):
                    for name in files:
                        self._make_writable(Path(root) / name)
                    for name in dirs:
                        self._make_writable(Path(root) / name)
                self._make_writable(cache_dir)
                shutil.rmtree(cache_dir)
            self.load_tags_cache()
        except Exception:
            self.TAGS_CACHE = {}
    
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
    
    def get_tags(self, fname: str, rel_fname: str) -> List[Tag]:
        """Get tags for a file, using cache when possible."""
        # ponytail: skip files that can't have tree-sitter symbols — saves read+parse per file
        _SKIP_EXTS = {'.frag', '.vert', '.inc', '.icns', '.plist', '.entitlements',
                      '.cmake.in', '.h.in', '.cpp.in', '.hpp.in'}
        if Path(fname).suffix in _SKIP_EXTS or fname.endswith(('.cmake.in', '.h.in', '.cpp.in', '.hpp.in')):
            return []
        
        file_mtime = self.get_mtime(fname)
        if file_mtime is None:
            return []
        
        try:
            # Both diskcache.Cache and dict have .get() method
            cached_entry = self.TAGS_CACHE.get(fname)
                
            if cached_entry and cached_entry.get("mtime") == file_mtime:
                return cached_entry["data"]
        except SQLITE_ERRORS:
            self.tags_cache_error()
        
        # Cache miss or file changed
        tags = self.get_tags_raw(fname, rel_fname)
        
        try:
            self.TAGS_CACHE[fname] = {"mtime": file_mtime, "data": tags}
        except SQLITE_ERRORS:
            self.tags_cache_error()
        
        return tags
    
    def get_tags_raw(self, fname: str, rel_fname: str) -> List[Tag]:
        """Parse file to extract tags using Tree-sitter."""
        try:
            from grep_ast.tsl import get_language, get_parser
            from tree_sitter import Query, QueryCursor
        except ImportError:
            raise GrepAstNotAvailableError("grep-ast is required. Install with: pip install grep-ast")
            
        lang = detect_lang(fname)
        if not lang:
            return []
        
        try:
            language = get_language(lang)
            parser = get_parser(lang)
        except Exception as err:
            self.output_handlers['error'](f"Skipping file {fname}: {err}")
            return []
        
        scm_fname = get_scm_fname(lang)
        if not scm_fname:
            return []
        
        code = self.read_text_func_internal(fname)
        if not code:
            return []
        
        # ponytail: skip tree-sitter parse for files with no code — empty or whitespace-only
        # saves a parse() call per file, which is the bottleneck on large repos
        if not code.strip():
            return []
        
        try:
            tree = parser.parse(bytes(code, "utf-8"))
            
            # Load query from SCM file
            query_text = read_text(scm_fname, silent=True)
            if not query_text:
                return []
            
            query = Query(language, query_text)
            cursor = QueryCursor(query)
            captures = cursor.captures(tree.root_node)
            
            tags = []
            # Process captures as a dictionary
            for capture_name, nodes in captures.items():
                for node in nodes:
                    if "name.definition" in capture_name:
                        kind = "def"
                    elif "name.reference" in capture_name:
                        kind = "ref"
                    else:
                        # Skip other capture types like 'reference.call' if not needed for tagging
                        continue 
                    
                    line_num = node.start_point[0] + 1
                    # Handle potential None value
                    name = node.text.decode('utf-8') if node.text else ""
                    
                    tags.append(Tag(
                        rel_fname=rel_fname,
                        fname=fname,
                        line=line_num,
                        name=name,
                        kind=kind
                    ))
            
            return tags
            
        except Exception as e:
            self.output_handlers['error'](f"Error parsing {fname}: {e}")
            return []

    def get_symbols(self, fname: str, rel_fname: str) -> List[SymbolRecord]:
        """Extract SymbolRecord objects from a file's AST.

        Reuses get_tags_raw's parse logic but enriches each definition with
        end_line, signature, docstring, language, and tree-sitter node kind.
        Only returns definitions (not references).
        """
        try:
            from grep_ast.tsl import get_language, get_parser
            from tree_sitter import Query, QueryCursor
        except ImportError:
            return []

        lang = detect_lang(fname)
        if not lang:
            return []

        try:
            language = get_language(lang)
            parser = get_parser(lang)
        except Exception:
            return []

        scm_fname = get_scm_fname(lang)
        if not scm_fname:
            return []

        code = self.read_text_func_internal(fname)
        if not code or not code.strip():
            return []

        try:
            tree = parser.parse(bytes(code, "utf-8"))
            query_text = read_text(scm_fname, silent=True)
            if not query_text:
                return []

            query = Query(language, query_text)
            cursor = QueryCursor(query)
            captures = cursor.captures(tree.root_node)

            # Collect definition captures — parent nodes (for end_line, body)
            # and name nodes (for the actual identifier).
            # e.g. definition.function -> full function node
            #       name.definition.function -> just the identifier node
            # Use lists because multiple definitions share the same capture name.
            parent_nodes: Dict[str, list] = {}  # capture_name -> [node, ...]
            name_nodes: Dict[str, list] = {}    # capture_name -> [node, ...]
            for capture_name, nodes in captures.items():
                for node in nodes:
                    if "definition" in capture_name:
                        if "name." in capture_name:
                            name_nodes.setdefault(capture_name, []).append(node)
                        else:
                            parent_nodes.setdefault(capture_name, []).append(node)

            # Build pairs: each parent node gets matched with its name node
            # by position (both lists are ordered by appearance in the file).
            # Map tree-sitter definition kinds to SymbolRecord.type
            kind_map = {
                "definition.function": "function",
                "definition.class": "class",
                "definition.method": "method",
                "definition.constant": "variable",
                "definition.module": "import",
                "definition.interface": "type",
                "definition.type": "type",
                "definition.enum": "type",
            }

            records = []
            for capture_name, parents in parent_nodes.items():
                sym_type = kind_map.get(capture_name, "variable")
                name_list = name_nodes.get("name." + capture_name, [])
                # Deterministic name resolution: the identifier immediately
                # following the def/func/fn/class keyword in parent.children.
                # Order-independent; avoids stealing nested/sibling names.
                used_names = set()
                for i, parent in enumerate(parents):
                    name = ""
                    # Find the keyword child, then take the next identifier sibling
                    keyword_types = ("def", "func", "fn", "class", "type", "interface", "enum")
                    for idx, child in enumerate(parent.children):
                        if child.type in keyword_types:
                            for next_child in parent.children[idx + 1:]:
                                if next_child.type in ("identifier", "type_identifier", "property_identifier"):
                                    name = next_child.text.decode("utf-8", errors="ignore")
                                    break
                            break
                    # Fallback: byte-range match against a name_node inside parent
                    if not name:
                        name_node = None
                        for n in name_list:
                            if id(n) in used_names:
                                continue
                            if n.start_byte >= parent.start_byte and n.end_byte <= parent.end_byte:
                                name_node = n
                                used_names.add(id(n))
                                break
                        if name_node is not None:
                            name = name_node.text.decode("utf-8", errors="ignore")
                    if not name:
                        # Last resort: any identifier child
                        for child in parent.children:
                            if child.type in ("identifier", "type_identifier", "property_identifier"):
                                name = child.text.decode("utf-8", errors="ignore")
                                break
                    if not name:
                        name = parent.text.decode("utf-8", errors="ignore")
                    start_line = parent.start_point[0] + 1
                    end_line = parent.end_point[0] + 1

                    # Build signature from function/method parameters
                    signature = ""
                    if sym_type in ("function", "method"):
                        sig_parts = [name]

                        # Find parameter_list (C/C++), parameters (Python),
                        # or parameter nodes (Swift — uses `parameter` directly
                        # inside function_declaration, no list wrapper).
                        # May be nested inside function_declarator, not a
                        # direct child of parent. Walk the subtree.
                        params_node = None
                        ret_type_node = None

                        def _find_in_subtree(node, depth=0):
                            nonlocal params_node, ret_type_node
                            if params_node is not None and ret_type_node is not None:
                                return
                            if node.type in ("parameter_list", "parameters", "formal_parameters", "method_parameters"):
                                if params_node is None:
                                    params_node = node
                                return  # don't descend into params themselves
                            # Swift: collect multiple `parameter` siblings
                            if node.type == "parameter" and depth > 0:
                                if params_node is None:
                                    params_node = [node]
                                elif isinstance(params_node, list):
                                    params_node.append(node)
                                return
                            if node.type == "trailing_return_type":
                                if ret_type_node is None:
                                    ret_type_node = node
                                return
                            # Swift: inline `->` return type — the `user_type`
                            # sibling after `->` within the function_declaration
                            if (node.type == "user_type" and ret_type_node is None
                                    and depth == 1):
                                ret_type_node = node
                                return
                            for child in node.children:
                                _find_in_subtree(child, depth + 1)

                        _find_in_subtree(parent)

                        if params_node:
                            if isinstance(params_node, list):
                                # Swift: reconstruct from individual params
                                param_text = ", ".join(
                                    p.text.decode("utf-8", errors="ignore")
                                    for p in params_node
                                )
                                sig_parts.append(f"({param_text})")
                            else:
                                sig_parts.append(params_node.text.decode("utf-8", errors="ignore"))

                        # C++ direct return type: the type node before
                        # function_declarator (e.g. "void" in "void foo()")
                        # The parent is the function_declarator itself —
                        # the return type is on the enclosing declaration
                        # or field_declaration, before the declarator.
                        if ret_type_node is None:
                            decl = parent.parent  # declaration or field_declaration
                            if decl and decl.type in ("declaration", "field_declaration",
                                                      "function_definition"):
                                for child in decl.children:
                                    # Skip storage qualifiers
                                    if child.type in ("storage_class_specifier",
                                                      "virtual_specifier",
                                                      "inline_specifier",
                                                      "virtual"):
                                        continue
                                    if child is parent:  # hit the function_declarator — no return type
                                        break
                                    # Don't use the function_declarator as return type
                                    if child.type == "function_declarator":
                                        break
                                    # Found a type-ish node before the declarator
                                    t = child.text.decode("utf-8", errors="ignore")
                                    if t.strip():
                                        ret_type_node = child
                                        break

                        # Generic return-type fallback: find a return-type node
                        # among parent's direct children. Handles Java (type_id
                        # or void_type before formal_parameters), Go (type_id
                        # or pointer_type after parameter_list), Rust (generic
                        # or primitive_type after ->), Swift (user_type after ->).
                        # ponytail: heuristic by node-type set, not per-language
                        # branches. Skips function/identifier/params/body nodes.
                        _RETURN_TYPE_NODES = frozenset({
                            "type_identifier", "void_type", "integral_type",
                            "boolean_type", "primitive_type", "generic_type",
                            "pointer_type", "user_type", "type_specifier",
                            "predefined_type",  # C# (void, int, bool, etc.)
                        })
                        _SKIP_NODES = frozenset({
                            "->", "pub", "private", "protected", "internal",
                            "extern", "async", "unsafe", "const", "static",
                            "virtual", "inline", "visibility_modifier",
                            "modifiers", "function_modifier", "fn", "func",
                            "function", "method", "identifier", "simple_identifier",
                            "(", ")", "{", "}", ";", "async", "override",
                            "parameter", "parameter_declaration",
                        })
                        _PARAMS_BODY_NODES = frozenset({
                            "block", "function_body", "body", "compound_statement",
                            "formal_parameters", "parameter_list", "parameters",
                            "method_parameters",  # Ruby
                        })
                        if ret_type_node is None:
                            # ponytail: C# return type can be an identifier
                            # (user-defined class) — skip the method name
                            # identifier specifically, then allow identifier.
                            _name_text = name
                            for c in parent.children:
                                if c.type in _SKIP_NODES and c.type != "identifier":
                                    continue
                                if c.type == "identifier" and c.text.decode("utf-8", "ignore") == _name_text:
                                    continue  # method name, not return type
                                if c.type in _PARAMS_BODY_NODES:
                                    continue  # params/body — keep scanning for return
                                if c.type in _RETURN_TYPE_NODES or c.type == "identifier":
                                    ret_type_node = c
                                    break

                        if ret_type_node:
                            ret_text = ret_type_node.text.decode("utf-8", errors="ignore")
                            # trailing_return_type (C++/Swift) text already
                            # starts with "-> " — don't double-add the arrow.
                            if ret_type_node.type == "trailing_return_type":
                                sig_parts.append(" " + ret_text)
                            else:
                                sig_parts.append(" -> " + ret_text)

                        signature = " ".join(sig_parts)

                    # Extract docstring (first string in function/class body)
                    docstring = ""
                    if sym_type in ("function", "method", "class"):
                        for child in parent.children:
                            if child.type == "block":
                                for bc in child.children:
                                    if bc.type == "expression_statement":
                                        for bc2 in bc.children:
                                            if bc2.type in ("string", "raw_string", "string_fragment"):
                                                docstring = bc2.text.decode("utf-8", errors="ignore").strip("\"'")
                                                break
                                    elif bc.type in ("string", "raw_string"):
                                        docstring = bc.text.decode("utf-8", errors="ignore").strip("\"'")
                                        break
                                if docstring:
                                    break

                    records.append(SymbolRecord(
                        name=name,
                        type=sym_type,
                        file=fname,
                        line=start_line,
                        end_line=end_line,
                        signature=signature,
                        docstring=docstring,
                        language=lang,
                        kind=capture_name,
                    ))

            return records

        except Exception as e:
            self.output_handlers['error'](f"Error extracting symbols from {fname}: {e}")
            return []

    def get_all_references(self, fname: str, rel_fname: str) -> List[Dict]:
        """Extract reference captures from a file's AST.

        Returns list of dicts with keys: line, name, capture_type, node_type.
        capture_type is one of: call, type, class, implementation, module, macro.
        ponytail: uses @name.reference.* captures (identifier-only) not the
        full expression node text — tree-sitter captures the whole call
        expression as @reference.call but the identifier is @name.reference.call.
        """
        try:
            from grep_ast.tsl import get_language, get_parser
            from tree_sitter import Query, QueryCursor
        except ImportError:
            return []

        lang = detect_lang(fname)
        if not lang:
            return []

        try:
            language = get_language(lang)
            parser = get_parser(lang)
        except Exception:
            return []

        scm_fname = get_scm_fname(lang)
        if not scm_fname:
            return []

        code = self.read_text_func_internal(fname)
        if not code or not code.strip():
            return []

        try:
            tree = parser.parse(bytes(code, "utf-8"))
            query_text = read_text(scm_fname, silent=True)
            if not query_text:
                return []

            query = Query(language, query_text)
            cursor = QueryCursor(query)
            captures = cursor.captures(tree.root_node)

            refs = []
            for capture_name, nodes in captures.items():
                if "reference" not in capture_name:
                    continue
                # Only use @name.reference.* captures — these give the clean
                # identifier (e.g. "get_rel_fname"). The bare @reference.call
                # captures give the full expression (e.g. "self.get_rel_fname()")
                # which is too noisy for callers/callees.
                if not capture_name.startswith("name.reference."):
                    continue
                # Extract the capture type: e.g. "name.reference.call" -> "call"
                parts = capture_name.split(".")
                ref_type = parts[-1] if len(parts) >= 3 else "reference"
                for node in nodes:
                    name = node.text.decode("utf-8", errors="ignore") if node.text else ""
                    refs.append({
                        "line": node.start_point[0] + 1,
                        "name": name,
                        "capture_type": ref_type,
                        "node_type": node.type,
                    })
            return refs

        except Exception as e:
            self.output_handlers['error'](f"Error extracting references from {fname}: {e}")
            return []

    def _discover_files(self) -> List[str]:
        """Discover source files under self.root. Uses shared skip logic."""
        return discover_src_files(str(self.root), use_gitignore=True, exclude_globs=self.exclude_globs)

    _import_index_cache: Dict[str, Dict] = None  # type: ignore[assignment]

    def _build_import_index(self) -> Dict[str, Dict]:
        """Build import bindings and name resolver for all source files.

        Returns a dict with:
          - 'resolver': NameResolver instance
          - 'file_imports': {file_path: [ImportBinding, ...]}
        ponytail: one pass over all files, cached on the instance — Tricorder is
        per-call in the MCP server, so no cross-project stale-cache risk.
        """
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
        defs: Dict[str, List[Tuple[str, int]]] = defaultdict(list)
        refs: Dict[str, List[Tuple[str, int]]] = defaultdict(list)

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

        return dict(defs), dict(refs)

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
                                if callee_name == name:
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
        for sym in symbols:
            # C/C++ tree-sitter queries yield names like "stretchMonitors()" or
            # "init(SDL_Window* window, ...)" — strip trailing parens and/or
            # everything from the first '(' to get the base name for matching.
            sym_name = sym.name
            if '(' in sym_name:
                sym_name = sym_name.split('(', 1)[0]
            elif sym_name.endswith('()'):
                sym_name = sym_name[:-2]
            if sym_name == symbol_name:
                if line == 0 or sym.line == line:
                    target = sym
                    break
        if target is None:
            return None

        # Extract body: read the lines for this symbol, truncate to 500 chars
        code = self.read_text_func_internal(file_path)
        if not code:
            target.body = ""
            return target

        lines = code.splitlines()
        start = max(0, target.line - 1)
        end = min(len(lines), target.end_line)
        body_lines = lines[start:end]
        body_text = "\n".join(body_lines)
        target.body = body_text[:500]

        # Build in-file call graph for callers/callees
        graph = self.build_call_graph([file_path])
        file_graph = graph.get(file_path, {"definitions": {}, "references": []})
        file_refs = file_graph["references"]

        # In-file callers: lines in this file that reference this symbol's name
        callers = []
        for ref in file_refs:
            if ref["name"] == symbol_name:
                callers.append({"file": file_path, "line": ref["line"], "cross_file": False})

        # In-file callees: unique symbols this file's code calls (excluding self)
        callees = []
        seen = set()
        for ref in file_refs:
            if ref["name"] != symbol_name and ref["name"] not in seen:
                seen.add(ref["name"])
                callees.append({"name": ref["name"], "file": file_path, "line": ref["line"], "cross_file": False})

        # Cross-file callers: references to this symbol in OTHER files
        # ponytail: normalize path separators — cross-file index uses os.path
        # (backslashes on Windows) but file_path may have forward slashes.
        _np = file_path.replace("\\", "/")
        defs, refs = self._build_cross_file_index()
        for ref_file, ref_line in refs.get(symbol_name, []):
            if ref_file.replace("\\", "/") != _np:
                callers.append({"file": ref_file, "line": ref_line, "cross_file": True})

        # Cross-file callees: symbols defined in OTHER files that this file references
        # Uses import tracking to resolve qualified names
        import_data = self._build_import_index()
        resolver = import_data['resolver']

        for ref in file_refs:
            ref_name = ref["name"]
            if ref_name == symbol_name:
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

        return target

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
    
    def render_tree(self, abs_fname: str, rel_fname: str, lois: List[int]) -> str:
        """Render a code snippet with specific lines of interest."""
        code = self.read_text_func_internal(abs_fname)
        if not code:
            return ""
        
        # T0 mode (context_lines == 0): just render definition lines directly
        # TreeContext renders the full file with scope annotations, bloating
        # token cost 36x for large repos. Skip it when no context is needed.
        if self.context_lines == 0:
            lines = code.splitlines()
            result_lines = [rel_fname]
            for loi in sorted(set(lois)):
                if 1 <= loi <= len(lines):
                    result_lines.append(f"  {loi}: {lines[loi-1]}")
            return "\n".join(result_lines)
        
        # T1 mode: use TreeContext for context rendering
        try:
            if rel_fname not in self.tree_context_cache:
                self.tree_context_cache[rel_fname] = TreeContext(
                    rel_fname,
                    code,
                    color=False
                )
            
            tree_context = self.tree_context_cache[rel_fname]
            return tree_context.format(lois)
        except Exception:
            # Fallback to simple line extraction
            lines = code.splitlines()
            result_lines = [f"{rel_fname}:"]
            
            for loi in sorted(set(lois)):
                if 1 <= loi <= len(lines):
                    result_lines.append(f"{loi:4d}: {lines[loi-1]}")
            
            return "\n".join(result_lines)
    
    def to_tree(self, tags: List[Tuple[float, Tag]], chat_rel_fnames: Set[str], untagged_files: Optional[List[str]] = None) -> str:
        """Convert ranked tags to formatted tree output."""
        if not tags:
            return ""
        
        # Group tags by file
        file_tags = defaultdict(list)
        for rank, tag in tags:
            file_tags[tag.rel_fname].append((rank, tag))
        
        # Sort files by importance (max rank of their tags)
        sorted_files = sorted(
            file_tags.items(),
            key=lambda x: max(rank for rank, tag in x[1]),
            reverse=True
        )
        
        tree_parts = []
        grouped_files = defaultdict(list)
        for rel_fname, file_tag_list in sorted_files:
            grouped_files[Path(rel_fname).parent.as_posix()].append((rel_fname, file_tag_list))

        # Pre-compute line counts for files we're about to render
        file_abs_paths = {rel: str(self.root / rel) for rel, _ in sorted_files}
        file_line_counts = {}
        for rel, abs_path in file_abs_paths.items():
            code = self.read_text_func_internal(abs_path)
            if code:
                file_line_counts[rel] = len(code.splitlines())

        for group_name, files_in_group in sorted(grouped_files.items(), key=lambda item: (item[0] != '.', item[0])):
            group_parts = []
            for rel_fname, file_tag_list in files_in_group:
                lois = [tag.line for rank, tag in file_tag_list]
                if self.context_lines > 0:
                    expanded_lois = []
                    for loi in lois:
                        for offset in range(-self.context_lines, self.context_lines + 1):
                            expanded_lois.append(max(1, loi + offset))
                    lois = sorted(set(expanded_lois))

                abs_fname = str(self.root / rel_fname)
                max_rank = max(rank for rank, tag in file_tag_list)
                rendered = self.render_tree(abs_fname, rel_fname, lois)
                if not rendered:
                    continue

                rendered_lines = rendered.splitlines()
                first_line = rendered_lines[0]
                code_lines = rendered_lines[1:]
                lc = file_line_counts.get(rel_fname)
                if lc:
                    first_line = f"{rel_fname} ({lc} lines)"
                rank_line = f"(Rank value: {max_rank:.4f})\n"
                if len(set(rank for rank, _ in file_tag_list)) == 1 and all(
                    max(r for r, _ in file_tags) == max_rank for _, file_tags in sorted_files
                ):
                    rank_line = ""
                group_parts.append(
                    f"{first_line}\n{rank_line}\n\n" + "\n".join(code_lines)
                )

            if group_parts:
                header = "root" if group_name == "." else group_name
                tree_parts.append(f"{header}/\n" + "\n\n".join(group_parts))

        return "\n\n".join(tree_parts)
    
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
        force_refresh: bool = False
    ) -> Optional[str]:
        """Get the ranked tags map with caching."""
        cache_key = (
            tuple(sorted(chat_fnames)),
            tuple(sorted(other_fnames)),
            max_map_tokens,
            tuple(sorted(mentioned_fnames or [])),
            tuple(sorted(mentioned_idents or [])),
        )
        
        if not force_refresh and cache_key in self.map_cache:
            return self.map_cache[cache_key]
        
        result = self.get_ranked_tags_map_uncached(
            chat_fnames, other_fnames, max_map_tokens,
            mentioned_fnames, mentioned_idents
        )
        
        self.map_cache[cache_key] = result
        return result
    
    def get_ranked_tags_map_uncached(
        self,
        chat_fnames: List[str],
        other_fnames: List[str],
        max_map_tokens: int,
        mentioned_fnames: Optional[Set[str]] = None,
        mentioned_idents: Optional[Set[str]] = None
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
        
        while left <= right:
            mid = (left + right) // 2
            tree_output, tokens = try_tags(mid)
            
            if tree_output and tokens <= max_map_tokens:
                best_tree = tree_output
                left = mid + 1
            else:
                right = mid - 1
        
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
        
        return best_tree, file_report
    
    def get_repo_map(
        self,
        chat_files: Optional[List[str]] = None,
        other_files: Optional[List[str]] = None,
        mentioned_fnames: Optional[Set[str]] = None,
        mentioned_idents: Optional[Set[str]] = None,
        force_refresh: bool = False
    ) -> Tuple[Optional[str], FileReport]:
        """Generate the repository map with file report."""
        chat_files = chat_files or []
        other_files = other_files or []
            
        # Create empty report for error cases
        empty_report = FileReport({}, 0, 0, 0, untagged_files=[])
        
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
                mentioned_fnames, mentioned_idents, force_refresh
            )
        except RecursionError:
            self.output_handlers['error']("Disabling repo map, git repo too large?")
            self.max_map_tokens = 0
            return None, FileReport({}, 0, 0, 0, untagged_files=[])  # Ensure consistent return type
        
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
