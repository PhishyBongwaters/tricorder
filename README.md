# tricorder

A tool for exploring and understanding codebases. Generates repository maps with function prototypes, variable references, and dependency graphs.

## Features
- Full-repo symbol indexing (tree-sitter + ctags hybrid)
- PageRank-based relevance ranking
- Configurable token budgets with automatic truncation
- CLI and MCP tool interfaces
-  flag for uncompressed map generation (bypasses truncation)

##  Usage
```bash
tricorder --root /path/to/repo --full --output full_map.txt .
```
Bypasses token truncation to emit the complete symbol map.

## License
MIT
