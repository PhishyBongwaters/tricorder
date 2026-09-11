"""
Parser mixin — tree-sitter parsing + tags (from core.py).
"""
import os, sys, threading
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from typing import List, Dict, Optional
import os
from utils import Tag, SymbolRecord, detect_lang, read_text
_PARSER_TIMEOUT_S = float(os.environ.get("TRICORDER_PARSER_TIMEOUT_S", "5"))
_PARSER_CACHE: dict = {}  # lang -> (language, parser) ponytail: one per language, not per file
from scm import get_scm_fname

class ParserMixin:
    def _add_class_context_to_tags(self, tags: List[Tag]) -> List[Tag]:
        """Post-process tags to add class context to method names.
        
        For C++ methods inside a class, prefix the method name with the class name
        (e.g., 'AddToBuffer' becomes 'PCM::AddToBuffer').
        """
        if not tags:
            return tags
        
        # Sort tags by line number to process in source order
        sorted_tags = sorted(tags, key=lambda t: t.line)
        
        result = []
        current_class = None
        
        for tag in sorted_tags:
            if tag.kind == "def" and tag.name and tag.name[0].isupper():
                # Heuristic: class names typically start with uppercase
                # Check if this looks like a class definition (no parentheses)
                if '(' not in tag.name and '::' not in tag.name:
                    current_class = tag.name
                    result.append(tag)
                    continue
            
            # For methods/functions, if we're in a class context, prefix with class name
            if tag.kind == "def" and current_class and '(' in tag.name:
                # This looks like a method definition
                new_name = f"{current_class}::{tag.name}"
                # Create new tag with updated name
                new_tag = Tag(
                    rel_fname=tag.rel_fname,
                    fname=tag.fname,
                    line=tag.line,
                    name=f"{current_class}::{tag.name}",
                    kind=tag.kind
                )
                result.append(new_tag)
            else:
                result.append(tag)
        
        return result

    def _parse_with_timeout(self, parser, code: str, fname: str):
        """TC-004: parse in a worker thread with a hard wall-clock timeout.

        tree-sitter has no native parse timeout; a pathological file can hang
        parsing in-process and stall the agent workflow. We run the parse in a
        daemon worker thread and join with _PARSER_TIMEOUT_S; on timeout (or
        error) we return None so the caller skips the file gracefully.

        ponytail: one worker thread per parse, join-timeout. Bounded hang
        window; memory bounded by the single file. Crash-isolation (a C-level
        parser fault) needs a subprocess — upgrade path if adversarial input
        proves able to segfault the parser.
        """
        result: dict = {}

        def _run():
            try:
                result["tree"] = parser.parse(bytes(code, "utf-8"))
            except Exception as e:  # noqa: BLE001 - any parse failure is skippable
                result["err"] = e

        t = threading.Thread(target=_run, daemon=True)
        t.start()
        t.join(_PARSER_TIMEOUT_S)
        if t.is_alive():
            self.output_handlers["warning"](
                f"Parse timeout exceeded after {_PARSER_TIMEOUT_S}s: "
                f"{fname} skipped (parser exceeded limit)"
            )
            return None
        if "err" in result:
            self.output_handlers["error"](f"Error parsing {fname}: {result['err']}")
            return None
        return result.get("tree")

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
            cached = _PARSER_CACHE.get(lang)
            if cached is not None:
                language, parser = cached
            else:
                language = get_language(lang)
                parser = get_parser(lang)
                _PARSER_CACHE[lang] = (language, parser)
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
            tree = self._parse_with_timeout(parser, code, fname)
            if tree is None:
                return []
            
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

    def _enclosing_class_name(self, node):
        """Walk up to the nearest enclosing class/struct definition name.

        Handles layouts where the function sits inside a class_declaration /
        struct_declaration / impl_item rather than directly.
        """
        cur = node.parent
        cls_types = ("class_declaration", "struct_declaration", "class_specifier",
                     "impl_item", "class_definition")
        while cur is not None:
            if cur.type in cls_types:
                for child in cur.children:
                    if child.type in ("identifier", "type_identifier",
                                       "class_identifier", "scoped_identifier"):
                        return child.text.decode("utf-8", errors="ignore")
                return ""
            cur = cur.parent
        return ""

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
            tree = self._parse_with_timeout(parser, code, fname)
            if tree is None:
                return []
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

                    # Scope the name to its enclosing class/struct (C/C++/Rust
                    # use '::'); e.g. void Foo::bar() -> "Foo::bar".
                    # ponytail: only for the ::-scoped languages, so Python
                    # stays dotted and isn't mis-scoped.
                    if lang in ("cpp", "c", "rust") and "::" not in name:
                        scope = self._enclosing_class_name(parent)
                        if scope:
                            name = f"{scope}::{name}"

                    start_line = parent.start_point[0] + 1
                    end_line = parent.end_point[0] + 1
                    # ponytail: tree-sitter queries capture function_declarator
                    # (signature only) not function_definition (full body).
                    # Walk up to function_definition to get the real end_line.
                    if sym_type in ("function", "method") and parent.type == "function_declarator":
                        func_def = parent.parent
                        if func_def and func_def.type == "function_definition":
                            end_line = func_def.end_point[0] + 1

                    # Build signature from function/method parameters
                    signature = ""
                    if sym_type in ("function", "method"):
                        sig_parts = [name]

                        # Python: preserve the 'async' keyword on async def.
                        if lang == "python" and parent.children and \
                                parent.children[0].type == "async":
                            sig_parts = ["async", name]

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
            tree = self._parse_with_timeout(parser, code, fname)
            if tree is None:
                return []
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

