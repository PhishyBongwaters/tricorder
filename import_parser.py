"""Language-agnostic import parsing for qualified name resolution.

Each language has a parser that walks the tree-sitter AST and extracts
import bindings: local_name -> qualified_name -> source_file.

Ponytail: minimal, no framework, one function per language.
"""

import os
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Tuple
from abc import ABC, abstractmethod


@dataclass
class ImportBinding:
    """One import binding: what name is available locally, what it resolves to."""
    local_name: str          # name used in code (e.g. 'Path', 'osp', 'db')
    qualified_name: str      # full dotted path (e.g. 'pathlib.Path', 'os.path')
    source_file: str         # absolute path of the file containing the import
    source_module: str       # module path (e.g. 'pathlib', 'os.path', './bar')
    is_from_import: bool     # True for `from X import Y`, False for `import X`
    is_star: bool = False    # True for `from X import *`
    is_static: bool = False  # True for static imports (Java, C#)
    line: int = 0            # line number of the import statement


class ImportParser(ABC):
    """Base class for language-specific import parsers."""

    @abstractmethod
    def parse(self, file_path: str, parser, code: bytes) -> List[ImportBinding]:
        """Parse import statements from a file's AST.

        Args:
            file_path: absolute path to the file
            parser: tree-sitter Parser instance
            code: raw bytes of the file

        Returns:
            List of ImportBinding objects
        """
        ...


# ── Python ──────────────────────────────────────────────────────────────────

class PythonImportParser(ImportParser):
    """Parse Python import statements from tree-sitter AST."""

    def parse(self, file_path: str, parser, code: bytes) -> List[ImportBinding]:
        tree = parser.parse(code)
        bindings = []
        self._extract_imports(tree.root_node, file_path, bindings, relative_prefix='')
        return bindings

    def _extract_imports(self, node, file_path: str, bindings: list, relative_prefix: str):
        for child in node.children:
            if child.type == 'import_statement':
                self._parse_import_statement(child, file_path, bindings, relative_prefix)
            elif child.type == 'import_from_statement':
                self._parse_import_from(child, file_path, bindings, relative_prefix)
            else:
                self._extract_imports(child, file_path, bindings, relative_prefix)

    def _parse_import_statement(self, node, file_path: str, bindings: list, relative_prefix: str):
        """Handle: import X, import X.Y, import X as Z, import X, Y"""
        children = list(node.children)
        # Skip 'import' keyword
        i = 1
        while i < len(children):
            child = children[i]
            if child.type == ',':
                i += 1
                continue
            if child.type == 'dotted_name':
                name = child.text.decode('utf-8', errors='ignore')
                bindings.append(ImportBinding(
                    local_name=name.split('.')[-1] if '.' in name else name,
                    qualified_name=relative_prefix + name if relative_prefix else name,
                    source_file=file_path,
                    source_module=name,
                    is_from_import=False,
                    line=child.start_point[0] + 1,
                ))
            elif child.type == 'aliased_import':
                # import X.Y as Z
                parts = list(child.children)
                dotted = None
                alias = None
                for p in parts:
                    if p.type == 'dotted_name' and dotted is None:
                        dotted = p
                    elif p.type == 'identifier':
                        alias = p
                if dotted and alias:
                    name = dotted.text.decode('utf-8', errors='ignore')
                    alias_name = alias.text.decode('utf-8', errors='ignore')
                    bindings.append(ImportBinding(
                        local_name=alias_name,
                        qualified_name=relative_prefix + name if relative_prefix else name,
                        source_file=file_path,
                        source_module=name,
                        is_from_import=False,
                        line=alias.start_point[0] + 1,
                    ))
            i += 1

    def _parse_import_from(self, node, file_path: str, bindings: list, relative_prefix: str):
        """Handle: from X import Y, from X.Y import Z as W, from . import A, from ..B import C"""
        children = list(node.children)
        module = ''
        is_relative = False
        is_star = False

        # Find the module (dotted_name or relative_import) and 'import' keyword
        module_node = None
        import_idx = None
        for i, child in enumerate(children):
            if child.type in ('dotted_name', 'relative_import') and module_node is None:
                module_node = child
            elif child.type == 'import':
                import_idx = i
                break

        if module_node is None or import_idx is None:
            return

        module = module_node.text.decode('utf-8', errors='ignore')
        if module_node.type == 'relative_import':
            is_relative = True

        # Build relative prefix from the number of dots
        if is_relative:
            dots = module.count('.')
            relative_prefix = '.' * dots
            module = ''

        # Parse imported names after 'import' keyword
        for i in range(import_idx + 1, len(children)):
            child = children[i]
            if child.type == ',':
                continue
            if child.type == '*':
                is_star = True
                bindings.append(ImportBinding(
                    local_name='*',
                    qualified_name=relative_prefix + module if relative_prefix else module,
                    source_file=file_path,
                    source_module=module,
                    is_from_import=True,
                    is_star=True,
                    line=child.start_point[0] + 1,
                ))
            elif child.type == 'wildcard_import':
                is_star = True
                bindings.append(ImportBinding(
                    local_name='*',
                    qualified_name=relative_prefix + module if relative_prefix else module,
                    source_file=file_path,
                    source_module=module,
                    is_from_import=True,
                    is_star=True,
                    line=child.start_point[0] + 1,
                ))
            elif child.type == 'dotted_name':
                name = child.text.decode('utf-8', errors='ignore')
                bindings.append(ImportBinding(
                    local_name=name,
                    qualified_name=relative_prefix + module + '.' + name if (relative_prefix or module) else name,
                    source_file=file_path,
                    source_module=module,
                    is_from_import=True,
                    line=child.start_point[0] + 1,
                ))
            elif child.type == 'aliased_import':
                parts = list(child.children)
                dotted = None
                alias = None
                for p in parts:
                    if p.type == 'dotted_name' and dotted is None:
                        dotted = p
                    elif p.type == 'identifier':
                        alias = p
                if dotted and alias:
                    name = dotted.text.decode('utf-8', errors='ignore')
                    alias_name = alias.text.decode('utf-8', errors='ignore')
                    bindings.append(ImportBinding(
                        local_name=alias_name,
                        qualified_name=relative_prefix + module + '.' + name if (relative_prefix or module) else name,
                        source_file=file_path,
                        source_module=module,
                        is_from_import=True,
                        line=alias.start_point[0] + 1,
                    ))


# ── JavaScript / TypeScript ─────────────────────────────────────────────────

class JavaScriptImportParser(ImportParser):
    """Parse JS/TS import/export statements from tree-sitter AST."""

    def parse(self, file_path: str, parser, code: bytes) -> List[ImportBinding]:
        tree = parser.parse(code)
        bindings = []
        self._extract_imports(tree.root_node, file_path, bindings)
        return bindings

    def _extract_imports(self, node, file_path: str, bindings: list):
        for child in node.children:
            if child.type == 'import_statement':
                self._parse_import(child, file_path, bindings)
            elif child.type == 'import_expression':
                self._parse_dynamic_import(child, file_path, bindings)
            elif child.type == 'lexical_declaration':
                self._parse_require(child, file_path, bindings)
            else:
                self._extract_imports(child, file_path, bindings)

    def _parse_import(self, node, file_path: str, bindings: list):
        """Handle: import X from 'Y', import { a, b as c } from 'Y', import * as ns from 'Y'"""
        children = list(node.children)
        source = ''

        # Find the source string
        for child in children:
            if child.type == 'string':
                source = child.children[1].text.decode('utf-8', errors='ignore') if len(child.children) > 1 else ''
                break

        # Find import_clause
        import_clause = None
        for child in children:
            if child.type == 'import_clause':
                import_clause = child
                break

        if not import_clause:
            return

        # Default import: import X from 'Y'
        for child in import_clause.children:
            if child.type == 'identifier':
                bindings.append(ImportBinding(
                    local_name=child.text.decode('utf-8', errors='ignore'),
                    qualified_name=child.text.decode('utf-8', errors='ignore'),
                    source_file=file_path,
                    source_module=source,
                    is_from_import=True,
                    line=child.start_point[0] + 1,
                ))

        # Named imports: import { a, b as c } from 'Y'
        for child in import_clause.children:
            if child.type == 'named_imports':
                self._parse_named_imports(child, source, file_path, bindings)

        # Namespace import: import * as ns from 'Y'
        for child in import_clause.children:
            if child.type == 'namespace_import':
                for c in child.children:
                    if c.type == 'identifier':
                        name = c.text.decode('utf-8', errors='ignore')
                        bindings.append(ImportBinding(
                            local_name=name,
                            qualified_name=name,
                            source_file=file_path,
                            source_module=source,
                            is_from_import=True,
                            line=c.start_point[0] + 1,
                        ))

    def _parse_named_imports(self, node, source: str, file_path: str, bindings: list):
        for child in node.children:
            if child.type == 'import_specifier':
                parts = list(child.children)
                original = None
                alias = None
                for p in parts:
                    if p.type == 'identifier' and original is None:
                        original = p
                    elif p.type == 'as':
                        pass
                    elif p.type == 'identifier' and alias is None:
                        alias = p
                if original:
                    orig_name = original.text.decode('utf-8', errors='ignore')
                    alias_name = alias.text.decode('utf-8', errors='ignore') if alias else orig_name
                    bindings.append(ImportBinding(
                        local_name=alias_name,
                        qualified_name=orig_name,
                        source_file=file_path,
                        source_module=source,
                        is_from_import=True,
                        line=original.start_point[0] + 1,
                    ))

    def _parse_dynamic_import(self, node, file_path: str, bindings: list):
        """Handle: const X = await import('./module')"""
        for child in node.children:
            if child.type == 'arguments':
                for a in child.children:
                    if a.type == 'string':
                        source = a.children[1].text.decode('utf-8', errors='ignore') if len(a.children) > 1 else ''
                        # Dynamic import returns the module namespace as the value
                        # We can't know the local binding without tracing the assignment

    def _parse_require(self, node, file_path: str, bindings: list):
        """Handle: const { a, b: c } = require('./module'), const X = require('./module')"""
        children = list(node.children)
        # Find variable_declarator
        for child in children:
            if child.type == 'variable_declarator':
                self._parse_require_binding(child, file_path, bindings)

    def _parse_require_binding(self, node, file_path: str, bindings: list):
        children = list(node.children)
        pattern = None
        source = ''

        for child in children:
            if child.type == 'identifier':
                local_name = child.text.decode('utf-8', errors='ignore')
            elif child.type in ('object_pattern', 'shorthand_property_identifier_pattern',
                                'pair_pattern', 'property_identifier'):
                pattern = child
            elif child.type == 'call_expression':
                for c in child.children:
                    if c.type == 'arguments':
                        for a in c.children:
                            if a.type == 'string':
                                source = a.children[1].text.decode('utf-8', errors='ignore') if len(a.children) > 1 else ''

        if pattern:
            self._parse_require_pattern(pattern, source, file_path, bindings)
        elif 'local_name' in dir():
            bindings.append(ImportBinding(
                local_name=local_name,
                qualified_name=local_name,
                source_file=file_path,
                source_module=source,
                is_from_import=True,
                line=children[0].start_point[0] + 1 if children else 0,
            ))

    def _parse_require_pattern(self, node, source: str, file_path: str, bindings: list):
        for child in node.children:
            if child.type == 'shorthand_property_identifier_pattern':
                name = child.text.decode('utf-8', errors='ignore')
                bindings.append(ImportBinding(
                    local_name=name,
                    qualified_name=name,
                    source_file=file_path,
                    source_module=source,
                    is_from_import=True,
                    line=child.start_point[0] + 1,
                ))
            elif child.type == 'pair_pattern':
                parts = list(child.children)
                original = None
                alias = None
                for p in parts:
                    if p.type == 'property_identifier' and original is None:
                        original = p
                    elif p.type == 'identifier':
                        alias = p
                if original:
                    orig_name = original.text.decode('utf-8', errors='ignore')
                    alias_name = alias.text.decode('utf-8', errors='ignore') if alias else orig_name
                    bindings.append(ImportBinding(
                        local_name=alias_name,
                        qualified_name=orig_name,
                        source_file=file_path,
                        source_module=source,
                        is_from_import=True,
                        line=original.start_point[0] + 1,
                    ))


# ── Java ────────────────────────────────────────────────────────────────────

class JavaImportParser(ImportParser):
    """Parse Java import statements from tree-sitter AST."""

    def parse(self, file_path: str, parser, code: bytes) -> List[ImportBinding]:
        tree = parser.parse(code)
        bindings = []
        self._extract_imports(tree.root_node, file_path, bindings)
        return bindings

    def _extract_imports(self, node, file_path: str, bindings: list):
        for child in node.children:
            if child.type == 'import_declaration':
                self._parse_import(child, file_path, bindings)
            else:
                self._extract_imports(child, file_path, bindings)

    def _parse_import(self, node, file_path: str, bindings: list):
        children = list(node.children)
        is_static = False
        scoped = None
        is_star = False

        for child in children:
            if child.type == 'static':
                is_static = True
            elif child.type == 'scoped_identifier':
                scoped = child
            elif child.type == 'asterisk':
                is_star = True

        if scoped:
            parts = []
            self._collect_scoped_parts(scoped, parts)
            module = '.'.join(parts[:-1]) if len(parts) > 1 else parts[0]
            simple_name = parts[-1]

            if is_star:
                bindings.append(ImportBinding(
                    local_name='*',
                    qualified_name=module,
                    source_file=file_path,
                    source_module=module,
                    is_from_import=True,
                    is_star=True,
                    is_static=is_static,
                    line=scoped.start_point[0] + 1,
                ))
            else:
                bindings.append(ImportBinding(
                    local_name=simple_name,
                    qualified_name='.'.join(parts),
                    source_file=file_path,
                    source_module=module,
                    is_from_import=True,
                    is_static=is_static,
                    line=scoped.start_point[0] + 1,
                ))

    def _collect_scoped_parts(self, node, parts: list):
        if node.type == 'scoped_identifier':
            for child in node.children:
                if child.type == 'identifier':
                    parts.append(child.text.decode('utf-8', errors='ignore'))
                elif child.type == 'scoped_identifier':
                    self._collect_scoped_parts(child, parts)
        elif node.type == 'identifier':
            parts.append(node.text.decode('utf-8', errors='ignore'))


# ── C++ ─────────────────────────────────────────────────────────────────────

class CppImportParser(ImportParser):
    """Parse C++ #include and using statements from tree-sitter AST.

    Ponytail: C++ includes don't create namespace bindings the way Python/JS do.
    We extract #include paths and using declarations, but qualified resolution
    is limited — C++ headers don't have a machine-readable module map.
    """

    def parse(self, file_path: str, parser, code: bytes) -> List[ImportBinding]:
        tree = parser.parse(code)
        bindings = []
        self._extract_imports(tree.root_node, file_path, bindings)
        return bindings

    def _extract_imports(self, node, file_path: str, bindings: list):
        for child in node.children:
            if child.type == 'preproc_include':
                self._parse_include(child, file_path, bindings)
            elif child.type == 'using_declaration':
                self._parse_using_decl(child, file_path, bindings)
            elif child.type == 'alias_declaration':
                self._parse_alias_decl(child, file_path, bindings)
            elif child.type == 'namespace_definition':
                self._parse_namespace(child, file_path, bindings)
            else:
                self._extract_imports(child, file_path, bindings)

    def _parse_include(self, node, file_path: str, bindings: list):
        for child in node.children:
            if child.type == 'system_lib_string':
                name = child.text.decode('utf-8', errors='ignore').strip('<>')
                bindings.append(ImportBinding(
                    local_name=name.split('.')[-1] if '.' in name else name,
                    qualified_name=name,
                    source_file=file_path,
                    source_module=name,
                    is_from_import=False,
                    line=child.start_point[0] + 1,
                ))
            elif child.type == 'string_literal':
                for c in child.children:
                    if c.type == 'string_content':
                        name = c.text.decode('utf-8', errors='ignore')
                        bindings.append(ImportBinding(
                            local_name=name.split('/')[-1].split('.')[0],
                            qualified_name=name,
                            source_file=file_path,
                            source_module=name,
                            is_from_import=False,
                            line=c.start_point[0] + 1,
                        ))

    def _parse_using_decl(self, node, file_path: str, bindings: list):
        children = list(node.children)
        for child in children:
            if child.type == 'identifier':
                bindings.append(ImportBinding(
                    local_name=child.text.decode('utf-8', errors='ignore'),
                    qualified_name=child.text.decode('utf-8', errors='ignore'),
                    source_file=file_path,
                    source_module='',
                    is_from_import=True,
                    line=child.start_point[0] + 1,
                ))

    def _parse_alias_decl(self, node, file_path: str, bindings: list):
        children = list(node.children)
        alias_name = None
        target_name = None
        for child in children:
            if child.type == 'type_identifier' and alias_name is None:
                alias_name = child.text.decode('utf-8', errors='ignore')
            elif child.type == 'type_descriptor':
                for c in child.children:
                    if c.type == 'type_identifier':
                        target_name = c.text.decode('utf-8', errors='ignore')
        if alias_name and target_name:
            bindings.append(ImportBinding(
                local_name=alias_name,
                qualified_name=target_name,
                source_file=file_path,
                source_module=target_name,
                is_from_import=True,
                line=alias_name and list(node.children)[1].start_point[0] + 1 if node.children else 0,
            ))

    def _parse_namespace(self, node, file_path: str, bindings: list):
        children = list(node.children)
        ns_name = None
        for child in children:
            if child.type == 'namespace_identifier':
                ns_name = child.text.decode('utf-8', errors='ignore')
                break
        if ns_name:
            bindings.append(ImportBinding(
                local_name=ns_name,
                qualified_name=ns_name,
                source_file=file_path,
                source_module=ns_name,
                is_from_import=True,
                line=children[0].start_point[0] + 1 if children else 0,
            ))


# ── Go ──────────────────────────────────────────────────────────────────────

class GoImportParser(ImportParser):
    """Parse Go import statements from tree-sitter AST."""

    def parse(self, file_path: str, parser, code: bytes) -> List[ImportBinding]:
        tree = parser.parse(code)
        bindings = []
        self._extract_imports(tree.root_node, file_path, bindings)
        return bindings

    def _extract_imports(self, node, file_path: str, bindings: list):
        for child in node.children:
            if child.type == 'import_declaration':
                self._parse_import(child, file_path, bindings)
            else:
                self._extract_imports(child, file_path, bindings)

    def _parse_import(self, node, file_path: str, bindings: list):
        children = list(node.children)
        # Single import: import alias "path"
        if len(children) >= 3:
            alias = None
            path = None
            for child in children:
                if child.type == 'identifier' and alias is None:
                    # Could be alias or path — check if next is identifier (alias) or string (path)
                    pass
                elif child.type == 'string':
                    path = child.text.decode('utf-8', errors='ignore').strip('"')
                elif child.type == 'identifier':
                    if alias is None and path is None:
                        # First identifier is alias if followed by another identifier
                        pass

        # Group import: import ( "path1", "path2" )
        for child in children:
            if child.type == 'import_spec_list':
                for c in child.children:
                    if c.type == 'import_spec':
                        self._parse_import_spec(c, file_path, bindings)

    def _parse_import_spec(self, node, file_path: str, bindings: list):
        children = list(node.children)
        alias = None
        path = None
        is_dot = False

        for child in children:
            if child.type == '.':
                is_dot = True
            elif child.type == 'identifier' and alias is None:
                alias = child.text.decode('utf-8', errors='ignore')
            elif child.type in ('string', 'interpreted_string_literal'):
                # Extract content from string literal
                for c in child.children:
                    if c.type in ('string_fragment', 'interpreted_string_literal_content'):
                        path = c.text.decode('utf-8', errors='ignore')
                        break
                if path is None:
                    path = child.text.decode('utf-8', errors='ignore').strip('"')

        if path:
            module_name = path.split('/')[-1]
            local = alias if alias else module_name
            if is_dot:
                local = '.'
            bindings.append(ImportBinding(
                local_name=local,
                qualified_name=path,
                source_file=file_path,
                source_module=path,
                is_from_import=True,
                line=children[0].start_point[0] + 1 if children else 0,
            ))


# ── Rust ────────────────────────────────────────────────────────────────────

class RustImportParser(ImportParser):
    """Parse Rust use statements from tree-sitter AST."""

    def parse(self, file_path: str, parser, code: bytes) -> List[ImportBinding]:
        tree = parser.parse(code)
        bindings = []
        self._extract_imports(tree.root_node, file_path, bindings)
        return bindings

    def _extract_imports(self, node, file_path: str, bindings: list):
        for child in node.children:
            if child.type == 'use_declaration':
                self._parse_use(child, file_path, bindings)
            else:
                self._extract_imports(child, file_path, bindings)

    def _parse_use(self, node, file_path: str, bindings: list):
        children = list(node.children)
        path_parts = []
        alias = None
        is_glob = False
        line = children[0].start_point[0] + 1 if children else 0

        for child in children:
            if child.type == 'scoped_identifier':
                self._collect_scoped_parts(child, path_parts)
            elif child.type == 'use_as_clause':
                # use X as Y
                for c in child.children:
                    if c.type == 'scoped_identifier':
                        path_parts = []
                        self._collect_scoped_parts(c, path_parts)
                    elif c.type == 'identifier':
                        alias = c.text.decode('utf-8', errors='ignore')
            elif child.type == 'use_wildcard':
                # use X::*
                is_glob = True
                for c in child.children:
                    if c.type == 'scoped_identifier':
                        self._collect_scoped_parts(c, path_parts)
            elif child.type == '*':
                is_glob = True

        if path_parts:
            qualified = '::'.join(path_parts)
            local = alias if alias else path_parts[-1]
            bindings.append(ImportBinding(
                local_name=local,
                qualified_name=qualified,
                source_file=file_path,
                source_module=qualified,
                is_from_import=True,
                is_star=is_glob,
                line=line,
            ))

    def _collect_scoped_parts(self, node, parts: list):
        if node.type == 'scoped_identifier':
            for child in node.children:
                if child.type == 'identifier':
                    parts.append(child.text.decode('utf-8', errors='ignore'))
                elif child.type == 'scoped_identifier':
                    self._collect_scoped_parts(child, parts)
        elif node.type == 'identifier':
            parts.append(node.text.decode('utf-8', errors='ignore'))


# ── Registry ────────────────────────────────────────────────────────────────

PARSERS: Dict[str, ImportParser] = {
    'python': PythonImportParser(),
    'javascript': JavaScriptImportParser(),
    'typescript': JavaScriptImportParser(),
    'java': JavaImportParser(),
    'cpp': CppImportParser(),
    'c': CppImportParser(),
    'go': GoImportParser(),
    'rust': RustImportParser(),
}


def get_parser(language: str) -> Optional[ImportParser]:
    """Get the import parser for a language."""
    return PARSERS.get(language)


def parse_imports(file_path: str, language: str, parser, code: bytes) -> List[ImportBinding]:
    """Parse imports from a file. Convenience function."""
    lang_parser = get_parser(language)
    if lang_parser is None:
        return []
    return lang_parser.parse(file_path, parser, code)
