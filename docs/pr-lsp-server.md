# PR Spec: Language Server Protocol (LSP) Server (`tricorder-lsp`)

**Milestone**: New — M1.x (Scale & Usability, P1)  
**Branch**: `feature/m1.x-lsp-server`  
**Target**: New entry point `tricorder-lsp` + shared core with MCP server

---

## Problem Statement

Tricorder already provides code intelligence via MCP tools (`tricorder_scan`, `tricorder_symbols`, `tricorder_detect`, `tricorder_detail`). But MCP is **agent-centric** — designed for LLM consumption. Editors (VS Code, Zed, Neovim, Helix, Emacs) speak **LSP**, not MCP.

**Goal**: Expose the same symbol index, call graph, and cross-file resolution as a **standard LSP server** so any editor gets:
- Go to Definition
- Find References
- Hover (signature + docstring)
- Document Symbols (outline)
- Workspace Symbols (fuzzy search)
- Code Lens (caller count)

All without running an LLM. Pure deterministic tooling.

---

## Non-Goals

- LLM-powered completions / semantic search (out of scope per ROADMAP)
- Diagnostics / linting (no type checker)
- Formatting / refactoring
- Multi-root workspace (single project root per LSP instance; editors handle multi-root)
- Watch mode integration (separate PR; LSP can poll cache or run standalone)

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        tricorder-lsp                            │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐ │
│  │  LSP Loop   │  │  Request    │  │  Shared Core (read-only)│ │
│  │  (stdio/TCP)│──▶│  Router     │──▶│  • TAGS_CACHE (disk)   │ │
│  └─────────────┘  └─────────────┘  │  • Import Index        │ │
│                                    │  • Call Graph          │ │
│                                    │  • Symbol Records      │ │
│                                    └─────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

**Key principle**: LSP server is **read-only** on the cache. It never triggers a parse. The CLI (`tricorder` / `tricorder --watch`) builds the cache. LSP serves from it.

---

## LSP Capabilities (MVP)

| LSP Method | tricorder Source | Status |
|------------|------------------|--------|
| `initialize` | — | ✅ Required |
| `initialized` | — | ✅ Required |
| `shutdown` / `exit` | — | ✅ Required |
| `textDocument/didOpen` | Track open files for priority | ✅ |
| `textDocument/didChange` | No-op (read-only cache) | ✅ |
| `textDocument/didClose` | Track closed files | ✅ |
| **`textDocument/definition`** | `tricorder_detail` → `callers` (def location) | ✅ MVP |
| **`textDocument/references`** | `tricorder_detail` → `callers` (all refs) | ✅ MVP |
| **`textDocument/hover`** | `tricorder_detail` → signature + docstring + body | ✅ MVP |
| **`textDocument/documentSymbol`** | `tricorder_symbols` (file filter) | ✅ MVP |
| **`workspace/symbol`** | `tricorder_symbols` (query + type filter) | ✅ MVP |
| `textDocument/codeLens` | Caller count per definition | 🔮 Nice-to-have |
| `textDocument/prepareCallHierarchy` | `tricorder_detail` → `callers`/`callees` | 🔮 v2 |

---

## Request Mapping

### `textDocument/definition`
```python
# Client: position in file X
# Server:
# 1. Find symbol at position (use tree-sitter query on open file or cached tags)
# 2. Look up in TAGS_CACHE for definition location
# 3. Return Location(uri, range)
```

### `textDocument/references`
```python
# Client: position in file X
# Server:
# 1. Find symbol at position
# 2. Get callers from call graph (cross-file + in-file)
# 3. Return Location[] (all references)
```

### `textDocument/hover`
```python
# Client: position in file X
# Server:
# 1. Find symbol at position
# 2. Get SymbolRecord from cache
# 3. Return MarkupContent: signature + docstring + body preview
```

### `textDocument/documentSymbol`
```python
# Client: file X
# Server:
# 1. Get all SymbolRecords for file from cache
# 2. Build DocumentSymbol[] hierarchy (namespace → class → method)
# 3. Return array
```

### `workspace/symbol`
```python
# Client: query string (fuzzy)
# Server:
# 1. Call tricorder_symbols(query=query, limit=100)
# 2. Return SymbolInformation[] (name, kind, location, containerName)
```

---

## Implementation Plan

### 1. New Entry Point: `tricorder_lsp.py`

```python
#!/usr/bin/env python3
"""
tricorder-lsp — Language Server Protocol server for code intelligence.
Reads from tricorder's on-disk cache (.repomap.tags.cache.v1/).
"""

import asyncio
import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from pygls.server import LanguageServer
from lsprotocol.types import *

# Reuse tricorder core (read-only)
sys.path.insert(0, str(Path(__file__).resolve().parent))
from core import Tricorder
from utils import discover_src_files, read_text, SymbolRecord

class TricorderLanguageServer(LanguageServer):
    def __init__(self, project_root: str, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.project_root = Path(project_root).resolve()
        self.tricorder = Tricorder(
            root=str(self.project_root),
            verbose=False,
        )
        self.open_files: Dict[str, str] = {}  # uri -> content
    
    def _get_symbol_at_position(self, uri: str, position: Position) -> Optional[SymbolRecord]:
        """Find symbol at cursor using cached tags + open file content."""
        # 1. Get file path from URI
        file_path = Path(uri.replace("file://", ""))
        rel_path = file_path.relative_to(self.project_root)
        
        # 2. Get cached tags for this file
        tags = self.tricorder.get_tags(str(file_path), str(rel_path))
        
        # 3. Find tag containing position
        for tag in tags:
            if tag.line == position.line + 1:  # LSP is 0-indexed
                # Get full symbol record
                return self.tricorder.get_symbol_detail(str(file_path), tag.name, tag.line)
        return None

# Register handlers
server = TricorderLanguageServer("tricorder-lsp", "0.1.0")

@server.feature(TEXT_DOCUMENT_DEFINITION)
async def definition(ls: TricorderLanguageServer, params: DefinitionParams):
    symbol = ls._get_symbol_at_position(params.text_document.uri, params.position)
    if not symbol:
        return None
    # Definition location
    return Location(
        uri=f"file://{symbol.file}",
        range=Range(
            start=Position(line=symbol.line_start - 1, character=0),
            end=Position(line=symbol.line_end - 1, character=0)
        )
    )

@server.feature(TEXT_DOCUMENT_REFERENCES)
async def references(ls: TricorderLanguageServer, params: ReferenceParams):
    symbol = ls._get_symbol_at_position(params.text_document.uri, params.position)
    if not symbol:
        return []
    
    # Get callers from call graph (already cross-file resolved)
    detail = ls.tricorder.get_symbol_detail(symbol.file, symbol.name, symbol.line)
    if not detail or not detail.callers:
        return []
    
    locations = []
    for caller in detail.callers:
        locations.append(Location(
            uri=f"file://{caller['file']}",
            range=Range(
                start=Position(line=caller['line'] - 1, character=0),
                end=Position(line=caller['line'] - 1, character=80)
            )
        ))
    return locations

@server.feature(TEXT_DOCUMENT_HOVER)
async def hover(ls: TricorderLanguageServer, params: HoverParams):
    symbol = ls._get_symbol_at_position(params.text_document.uri, params.position)
    if not symbol:
        return None
    
    detail = ls.tricorder.get_symbol_detail(symbol.file, symbol.name, symbol.line)
    if not detail:
        return None
    
    # Build markdown hover
    parts = []
    if detail.signature:
        parts.append(f"```python\n{detail.signature}\n```")
    if detail.docstring:
        parts.append(detail.docstring)
    if detail.body:
        parts.append(f"```python\n{detail.body[:500]}\n```")
    
    return Hover(contents=MarkupContent(kind="markdown", value="\n\n".join(parts)))

@server.feature(TEXT_DOCUMENT_DOCUMENT_SYMBOL)
async def document_symbol(ls: TricorderLanguageServer, params: DocumentSymbolParams):
    file_path = Path(params.text_document.uri.replace("file://", ""))
    rel_path = file_path.relative_to(ls.project_root)
    symbols = ls.tricorder.get_symbols(str(file_path), str(rel_path))
    
    # Convert to DocumentSymbol hierarchy
    result = []
    for sym in symbols:
        result.append(DocumentSymbol(
            name=sym.name,
            kind=SymbolKind[sym.type.upper()] if sym.type.upper() in SymbolKind.__members__ else SymbolKind.Function,
            range=Range(
                start=Position(line=sym.line_start - 1, character=0),
                end=Position(line=sym.line_end - 1, character=0)
            ),
            selection_range=Range(
                start=Position(line=sym.line - 1, character=0),
                end=Position(line=sym.line - 1, character=len(sym.name))
            ),
            children=None  # Could build hierarchy from nesting
        ))
    return result

@server.feature(WORKSPACE_SYMBOL)
async def workspace_symbol(ls: TricorderLanguageServer, params: WorkspaceSymbolParams):
    # Delegate to tricorder_symbols logic
    query = params.query
    all_files = discover_src_files(str(ls.project_root))
    results = []
    
    for file_path in all_files:
        rel_path = str(Path(file_path).relative_to(ls.project_root))
        symbols = ls.tricorder.get_symbols(file_path, rel_path)
        for sym in symbols:
            if query.lower() in sym.name.lower():
                results.append(SymbolInformation(
                    name=sym.name,
                    kind=SymbolKind[sym.type.upper()] if sym.type.upper() in SymbolKind.__members__ else SymbolKind.Function,
                    location=Location(
                        uri=f"file://{file_path}",
                        range=Range(
                            start=Position(line=sym.line_start - 1, character=0),
                            end=Position(line=sym.line_end - 1, character=0)
                        )
                    ),
                    container_name=sym.container_name or ""
                ))
    
    return results[:100]  # Cap

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, help="Project root (absolute path)")
    parser.add_argument("--stdio", action="store_true", help="Run over stdio (default)")
    parser.add_argument("--tcp", action="store_true", help="Run over TCP")
    parser.add_argument("--port", type=int, default=9229, help="TCP port")
    args = parser.parse_args()
    
    server.project_root = Path(args.root).resolve()
    
    if args.tcp:
        server.start_tcp("127.0.0.1", args.port)
    else:
        server.start_io()

if __name__ == "__main__":
    main()
```

### 2. Dependencies

```txt
# requirements.txt additions
pygls>=1.0.0      # LSP server framework
lsprotocol>=2024.0.0  # LSP types
```

### 3. pyproject.toml Entry Point

```toml
[project.scripts]
tricorder = "tricorder:main"
tricorder-mcp = "tricorder_server:main"
tricorder-lsp = "tricorder_lsp:main"
```

### 4. Editor Configuration Examples

**VS Code** (`.vscode/settings.json`):
```json
{
  "tricorder.lsp.enabled": true,
  "tricorder.lsp.projectRoot": "${workspaceFolder}"
}
```

**Neovim** (`nvim-lspconfig`):
```lua
require'lspconfig'.tricorder.setup{
  cmd = {'tricorder-lsp', '--root', vim.fn.getcwd(), '--stdio'},
  filetypes = {'python', 'javascript', 'typescript', 'rust', 'go', 'cpp', 'java'},
  root_dir = require'lspconfig'.util.root_pattern('.git', 'pyproject.toml', 'Cargo.toml', 'go.mod'),
}
```

**Zed** (`settings.json`):
```json
{
  "lsp": {
    "tricorder": {
      "command": "tricorder-lsp",
      "args": ["--root", "{{project_root}}", "--stdio"]
    }
  }
}
```

---

## Cache Sharing Protocol

| Component | Cache Access |
|-----------|--------------|
| `tricorder` (CLI) | **Write** — builds `TAGS_CACHE`, import index, call graph |
| `tricorder --watch` | **Write** — incremental updates to `TAGS_CACHE` |
| `tricorder-mcp` | **Read** — queries cache via `Tricorder` methods |
| `tricorder-lsp` | **Read** — queries cache via `Tricorder` methods |

**No lock contention**: `diskcache` handles concurrent readers + single writer. LSP and MCP are read-only.

---

## Validation Gates

| Test | Command | Expected |
|------|---------|----------|
| Start LSP | `tricorder-lsp --root /project --stdio` | Server starts, responds to `initialize` |
| Go to Definition | Editor: `gd` on symbol | Jumps to definition (cross-file) |
| Find References | Editor: `gr` on symbol | Lists all callers (cross-file) |
| Hover | Editor: hover on symbol | Shows signature + docstring + body preview |
| Document Symbols | Editor: outline view | Shows file structure |
| Workspace Symbols | Editor: fuzzy search | Finds symbols across project |
| Cache freshness | Edit file → `tricorder --watch` updates → LSP reflects | No restart needed |
| Multiple editors | VS Code + Neovim on same project | Both work independently |

**Automated test**: `tests/test_lsp.py` (integration with `pygls` test client)

---

## Files to Create/Modify

| File | Status | Description |
|------|--------|-------------|
| `tricorder_lsp.py` | **New** | LSP server entry point |
| `pyproject.toml` | Modify | Add `tricorder-lsp` entry point |
| `requirements.txt` | Modify | Add `pygls`, `lsprotocol` |
| `tests/test_lsp.py` | **New** | LSP integration tests |
| `docs/lsp-setup.md` | **New** | Editor configuration guide |

---

## Backward Compatibility

- Zero impact on existing CLI, MCP, plugin
- New binary `tricorder-lsp` installed alongside `tricorder` and `tricorder-mcp`
- Shared cache means LSP benefits from CLI/watch updates automatically

---

## Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| `pygls` adds heavy deps | Optional extra: `pip install tricorder[lsp]`; core stays lean |
| Stale cache → wrong locations | LSP reads cache as-is; user runs `tricorder` or `--watch` to refresh |
| Position mapping (bytes vs chars) | Use `read_text` + line-based lookup; tree-sitter gives byte offsets, convert for LSP |
| Large projects → slow `workspace/symbol` | Cache all symbol names in memory at startup (lazy load); cap results at 100 |
| No type info for hover | Show what we have (signature + docstring); no fake types |

---

## Definition of Done

- [ ] `tricorder-lsp --root /project --stdio` starts and responds to `initialize`
- [ ] `textDocument/definition` works (cross-file via call graph)
- [ ] `textDocument/references` works (all callers)
- [ ] `textDocument/hover` shows signature + docstring + body
- [ ] `textDocument/documentSymbol` populates outline
- [ ] `workspace/symbol` fuzzy-searches across project
- [ ] Works with VS Code, Neovim, Zed (manual verification)
- [ ] `pytest tests/test_lsp.py -v` green
- [ ] SPEC.md updated with LSP section
- [ ] `docs/lsp-setup.md` created
- [ ] CHANGELOG entry

---

## Estimated Effort

- LSP server core: ~400 lines
- Editor config docs: ~100 lines
- Tests: ~200 lines
- **Total**: ~700 lines, 3–4 days

---

## Future Extensions (v2+)

- `textDocument/prepareCallHierarchy` + `textDocument/provideCallHierarchyIncoming/Outgoing` — full call tree navigation
- `textDocument/codeLens` — inline caller counts ("3 callers")
- `textDocument/semanticTokens` — syntax highlighting from tree-sitter
- Watch mode integration — LSP subscribes to cache invalidation events
- Multi-root workspace — aggregate multiple project roots