"""Name resolution: maps bare identifiers to qualified names via import bindings.

Architecture:
1. Each file's imports are parsed into ImportBinding objects.
2. A scope map is built: local_name -> List[qualified_name, source_file]
3. When resolving a bare identifier (e.g. 'Path' from 'Path("/tmp")'),
   we look it up in the scope map and return the qualified name.

Ponytail: simple dict-based scope, no fancy scoping rules.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from import_parser import ImportBinding


@dataclass
class Resolution:
    """Result of resolving a bare identifier."""
    bare_name: str
    qualified_name: str
    source_file: str
    source_line: int
    confidence: float  # 1.0 = exact match, 0.5 = ambiguous, 0.0 = unresolved


class NameResolver:
    """Resolves bare identifiers to qualified names using import bindings."""

    def __init__(self):
        # file_path -> List[ImportBinding]
        self.file_imports: Dict[str, List[ImportBinding]] = {}
        # local_name -> List[ImportBinding] (flattened across all files)
        self.global_scope: Dict[str, List[ImportBinding]] = {}

    def add_file(self, file_path: str, bindings: List[ImportBinding]):
        """Add import bindings for a file."""
        self.file_imports[file_path] = bindings
        for binding in bindings:
            if binding.local_name not in self.global_scope:
                self.global_scope[binding.local_name] = []
            self.global_scope[binding.local_name].append(binding)

    def resolve(self, bare_name: str, context_file: str) -> Resolution:
        """Resolve a bare identifier in the context of a file.

        Scope-aware: checks the context file's own imports first (local
        shadowing), then falls back to global scope. This prevents
        cross-file pollution where pathlib.Path wins over mypackage.Path
        just because it's a shorter qualified name.

        Args:
            bare_name: the unqualified name (e.g. 'Path', 'join')
            context_file: the file where the reference appears

        Returns:
            Resolution with qualified name and confidence
        """
        # Priority 0: local scope — check this file's own imports first
        local_bindings = self.file_imports.get(context_file, [])
        local_matches = [b for b in local_bindings if b.local_name == bare_name]
        if local_matches:
            # ponytail: single local match is definitive; multiple local
            # matches (e.g. from X import Y, from Z import Y) fall through
            # to global disambiguation below.
            if len(local_matches) == 1:
                c = local_matches[0]
                return Resolution(
                    bare_name=bare_name,
                    qualified_name=c.qualified_name,
                    source_file=c.source_file,
                    source_line=c.line,
                    confidence=1.0,
                )

        # Fallback: global scope (all imports across the repo)
        candidates = self.global_scope.get(bare_name, [])

        if not candidates:
            return Resolution(
                bare_name=bare_name,
                qualified_name=bare_name,
                source_file=context_file,
                source_line=0,
                confidence=0.0,
            )

        if len(candidates) == 1:
            c = candidates[0]
            return Resolution(
                bare_name=bare_name,
                qualified_name=c.qualified_name,
                source_file=c.source_file,
                source_line=c.line,
                confidence=1.0,
            )

        # Multiple candidates — try to disambiguate by context
        best = self._disambiguate(bare_name, candidates, context_file)
        return best

    def _disambiguate(self, bare_name: str, candidates: List[ImportBinding],
                      context_file: str) -> Resolution:
        """Pick the best candidate when multiple imports share the same bare name."""
        # Priority 1: same-file import (local shadowing)
        same_file = [c for c in candidates if c.source_file == context_file]
        if len(same_file) == 1:
            c = same_file[0]
            return Resolution(
                bare_name=bare_name,
                qualified_name=c.qualified_name,
                source_file=c.source_file,
                source_line=c.line,
                confidence=1.0,
            )

        # Priority 2: from-import (more specific than bare import)
        from_imports = [c for c in candidates if c.is_from_import]
        if len(from_imports) == 1:
            c = from_imports[0]
            return Resolution(
                bare_name=bare_name,
                qualified_name=c.qualified_name,
                source_file=c.source_file,
                source_line=c.line,
                confidence=0.8,
            )

        # Priority 3: shortest qualified name (most specific module)
        if candidates:
            best = min(candidates, key=lambda c: len(c.qualified_name))
            return Resolution(
                bare_name=bare_name,
                qualified_name=best.qualified_name,
                source_file=best.source_file,
                source_line=best.line,
                confidence=0.5,
            )

        return Resolution(
            bare_name=bare_name,
            qualified_name=bare_name,
            source_file=context_file,
            source_line=0,
            confidence=0.0,
        )

    def get_all_bindings(self, file_path: str) -> List[ImportBinding]:
        """Get all import bindings for a file."""
        return self.file_imports.get(file_path, [])

    def get_qualified_name(self, file_path: str, bare_name: str) -> Optional[str]:
        """Get the qualified name for a bare identifier in a file.

        Returns None if unresolved.
        """
        resolution = self.resolve(bare_name, file_path)
        if resolution.confidence > 0:
            return resolution.qualified_name
        return None
