# tricorder

**Star Trek-inspired code intelligence MCP server + Hermes plugin.**

tricorder scans codebases the way a Starfleet tricorder scans a planet: it senses, analyzes, and reports what's there — symbols, call graphs, signatures, references — without reading every file. You point it at a codebase; it tells you what matters.

Built on tree-sitter for parsing and PageRank for ranking, tricorder generates compressed maps that let humans and LLMs understand unfamiliar codebases at a fraction of the context cost.

---

## Origin Story

tricorder has a lineage worth telling.

### Generation 1: Aider

Paul Gauthier created [Aider](https://github.com/paul-gauthier/aider), an AI pair programmer. Aider includes a `RepoMap` class that uses tree-sitter to extract code symbols and PageRank to rank them by importance, producing a compressed "map" of a repository. This lets the LLM understand the codebase structure without reading every file — a fraction of the tokens, a fraction of the cost.

### Generation 2: RepoMapper

[Paul Davis (pdavis68)](https://github.com/pdavis68) reimplemented Aider's RepoMap from specifications, removed the Aider-specific dependencies, and made it a standalone CLI tool plus MCP server. He used a combination of Aider (with Claude 3.7), Cline (with Gemini 2.5 Pro), and various other LLM tools to build it. The result was RepoMapper — a general-purpose repo mapping tool that any MCP-compatible client could use.

Repo: https://github.com/pdavis68/RepoMapper

### Generation 3: The Fork

We forked RepoMapper and went deep on language coverage, correctness, and code intelligence:

- **8 critical bug fixes** — NameError, TypeError, cache path, duplicate definitions, dead variables, redundant checks, dedup edge cases, relative_to crash
- **73 tests** — zero existed in the original
- **10-language signature extraction** with return types — Python, JS/TS, C, C++, Java, Go, Rust, Swift, C#, Ruby
- **Cross-file call graph** — callers/callees with import resolution across files
- **Reference captures** — C `call_expression`/type refs, Swift `call_expression`/`navigation_expression`/`user_type` refs
- **Windows path normalization** — cross-file caller/callee false positives fixed (path separator mismatch)
- **`.h` → C++ mapping** — `grep_ast` mapped `.h` to C; overridden to map to C++
- **Mermaid graph output** with zero-tag file filtering
- **Tier system** (T0 definitions, T1 context) with token-aware escalation
- **MCP server** with 4 tools: `repo_map`, `search_symbols`, `search_identifiers`, `get_symbol_details`

### Generation 4: tricorder

This is the rebrand. RepoMapper worked, but it was a fork that had outgrown its name. tricorder is the same code, repackaged as a first-class Hermes plugin with:

- **Skills** bundled — usage patterns travel with the plugin
- **Slash commands** — `/scan`, `/findsym`, `/symbol` for interactive use
- **Lifecycle hooks** — auto-activation and context-aware enforcement

The name comes from the Star Trek tricorder — a handheld sensor device that scans, analyzes, and reports on unfamiliar environments. That's exactly what this tool does with codebases. 🖖

---

## Architecture

```
tricorder/
├── plugin.yaml              # Hermes plugin manifest
├── __init__.py              # Plugin entry point + tool registration
├── repomap_class.py         # Core: RepoMap class (parsing, ranking, call graph)
├── repomap_server.py        # MCP server (4 tools)
├── repomap.py               # CLI entry point
├── utils.py                 # Shared utilities (detect_lang, etc.)
├── name_resolver.py         # Cross-file import resolution
├── import_parser.py         # Language-specific import parsing
├── queries/
│   └── tree-sitter-language-pack/
│       ├── python-tags.scm
│       ├── javascript-tags.scm
│       ├── c-tags.scm
│       ├── cpp-tags.scm
│       ├── csharp-tags.scm
│       ├── ruby-tags.scm
│       ├── swift-tags.scm
│       └── ... (50+ languages via tree-sitter-language-pack)
├── skills/
│   ├── tricorder-mcp/       # MCP tool usage skill
│   └── tricorder-cli/       # CLI usage skill
├── commands/
│   └── tricorder.py         # Slash commands: /scan, /findsym, /symbol
├── hooks/
│   └── ...                  # Lifecycle hooks (TBD)
├── tests/                   # 73 tests (ported from RepoMapper fork)
├── README.md
├── LICENSE                  # MIT
├── requirements.txt
└── pyproject.toml
```

---

## MCP Tools (4)

### `repo_map`
Generate a ranked code map for a project directory. Writes to `output_file` to avoid context bloat.

```json
{
  "project_root": "/absolute/path/to/project",
  "token_limit": 2048,
  "tier": 0,
  "output_file": "/path/to/map.txt",
  "output_format": "text|mermaid",
  "chat_files": ["file.py"],
  "exclude_untagged": false
}
```

Returns: `{"map_file": "/path/to/map.txt", "token_estimate": N}` — never the full map inline.

### `search_symbols`
Structured symbol search with type and file filters. Returns full `SymbolRecord` data.

```json
{
  "project_root": "/absolute/path/to/project",
  "query": "auth",
  "type": "function|class|method|variable|import",
  "file": "auth.py",
  "limit": 50
}
```

### `search_identifiers`
Case-insensitive identifier search across all source files.

```json
{
  "project_root": "/absolute/path/to/project",
  "query": "main",
  "max_results": 50,
  "context_lines": 2,
  "include_definitions": true,
  "include_references": true
}
```

### `get_symbol_details`
Full details for a symbol: body, signature, docstring, callers, callees.

```json
{
  "project_root": "/absolute/path/to/project",
  "file": "auth.py",
  "name": "authenticate",
  "line": 42
}
```

Returns callers (in-file + cross-file with import resolution) and callees.

---

## Language Coverage

| Language | Refs | Sigs | Return Types | Notes |
|----------|------|------|-------------|-------|
| Python | ✓ | ✓ | ✓ | |
| JS/TS | ✓ | ✓ | ✓ | |
| C | ✓ | ✓ | ✓ | Reference captures: call_expression, type refs |
| C++ | ✓ | ✓ | ✓ | `.h` files map to C++ (not C) |
| Java | ✓ | ✓ | ✓ | Uses `formal_parameters` (not `parameter_list`) |
| Go | ✓ | ✓ | ✓ | |
| Rust | ✓ | ✓ | ✓ | `trailing_return_type` double-arrow fix |
| Swift | ✓ | ✓ | ✓ | Subtree walk for params (no list wrapper) |
| C# | ✓ | ✓ | ✓ | `predefined_type` + `identifier` return types |
| Ruby | ✓ | ✓ | ✓ | `method_parameters` param node |

---

## Slash Commands (planned)

| Command | Description |
|---------|-------------|
| `/scan <path>` | Generate a repo map for a directory, write to disk |
| `/findsym <name> [path]` | Search for a symbol by name across a project |
| `/symbol <file> <name>` | Get full symbol details (callers, callees, signature) |

---

## Lifecycle Hooks (planned)

- **Auto-detection**: When a project directory is opened, tricorder scans for source files and makes a T0 map available on-demand.
- **Context enforcement**: Hook intercepts `read_file` calls — if the file hasn't been identified via a tricorder map, suggest scanning first. Avoids blind full-file reads on large files.
- **Smart caching**: Map regeneration only when files have changed (mtime check). No redundant scans.

---

## Token Economy

The entire point of tricorder is context efficiency. An LLM agent understanding a codebase has two options:

1. **Read every file** — 32,620 tokens for a medium repo
2. **Use tricorder** — 491 tokens for the same repo (1.5% of full)

| Approach | Chars | Tokens |
|----------|-------|--------|
| Full repo scan | 133,432 | 32,620 |
| tricorder T0 map | 1,702 | 491 |
| **Savings** | **131,730** | **32,129 (98.5%)** |

### Tier system

- **Mermaid** — dependency graph (module relationships only). Cheapest.
- **T0** — definitions only (~14 tokens/tag). Locate a symbol.
- **T1** — definitions + context lines (~350 tokens/tag). Assess relevance.

Stop at the first tier that answers the question.

---

## License

MIT — same as Aider and RepoMapper. Fully open source.

---

## Attribution

tricorder builds on the work of:

1. **Paul Gauthier** — [Aider](https://github.com/paul-gauthier/aider) — the original RepoMap concept and implementation using tree-sitter + PageRank.

2. **Paul Davis (pdavis68)** — [RepoMapper](https://github.com/pdavis68/RepoMapper) — reimplemented Aider's RepoMap as a standalone CLI + MCP server, using LLMs to generate specs from Aider's code and then build from those specs.

3. **The Hermes Agent community** — for the plugin system, MCP client, and tool framework that tricorder plugs into.

The code in this repository is a rebrand and plugin-ification of the RepoMapper fork maintained at `http://127.0.0.1:3001/projects/repomapper.git`. The fork added 8 bug fixes, 73 tests, 10-language coverage, cross-file call graph analysis, and Windows compatibility — all of which carry forward to tricorder.

---

## Status

**Planning phase.** Code migration from RepoMapper fork to tricorder is pending. SPEC.md is the design document; actual build is next.
