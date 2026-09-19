# MCP Reference

Tricorder runs as an MCP server over **STDIO**. Start it with:

```bash
tricorder-mcp
# or: python tricorder_server.py
```

Register it in your MCP client:

```jsonc
// cline_mcp_settings.json
{ "mcpServers": { "tricorder": {
    "command": "/absolute/path/to/.venv/Scripts/tricorder-mcp.exe",
    "type": "stdio",
    "disabled": false,
    "timeout": 60,
    "args": []
} } }
```

```yaml
# ~/.hermes/config.yaml
mcp_servers:
  tricorder:
    command: "C:/absolute/path/to/tricorder/.venv/Scripts/tricorder-mcp.exe"
    args: []
```

Requires the `mcp` Python package (`pip install mcp`). A bundled skill
(`skills/tricorder/SKILL.md`) teaches agents the escalation ladder.

**Every response** carries provenance stamps: `source: "scanned_repository"`,
`trust: "untrusted_repository_content"`. Raw maps are wrapped in
`BEGIN/END UNTRUSTED REPOSITORY CONTEXT` markers. See
[Architecture](architecture.md#security-model).

All `project_root` values **must be absolute paths**. File params are rejected
if they resolve outside `project_root` (path containment).

---

## tricorder_scan

Generate a repository map: function prototypes and variables per file, plus
relevant related files.

| Param | Type | Default | Description |
|---|---|---|---|
| `project_root` | string | — | **Required.** Absolute path to the project. |
| `chat_files` | string[] | — | Files in the chat context — highest ranking. |
| `other_files` | string[] | — | Other relevant files — lowest ranking. |
| `mentioned_files` | string[] | — | Explicitly mentioned files — mid-level boost. |
| `mentioned_idents` | string[] | — | Explicitly mentioned identifiers — ranking boost. |
| `token_limit` | int | `8192` | Max tokens for the map. |
| `tier` | int | `0` | `0` = definitions only (cheapest); `1` = definitions + context lines. |
| `context_lines` | int | `3` | Context lines per definition when `tier=1`. |
| `output_format` | string | `"text"` | `"text"` for the map, `"mermaid"` for a dependency flowchart. |
| `output_file` | string | — | Write the map to this path instead of returning it. **Recommended for repos > 50 files** — the response then contains only the path + token estimate. |
| `exclude_unranked` | bool | `false` | Drop files with PageRank 0. |
| `exclude_globs` | string[] | — | POSIX globs (relative to `project_root`) excluded from auto-scan. |
| `force_refresh` | bool | `false` | Bust the cache and rescan. |
| `max_files` | int | `0` | Cap auto-scanned files (`0` = unlimited). |
| `max_context_window` | int | — | Adjusts the token limit when no chat files are given. |
| `dry_run` | bool | `false` | Return budget estimates only (`tags`, `tokens_per_tag`, `tags_at_budget`, `full_repo_estimate`). |
| `full` | bool | `false` | Emit the full map regardless of `token_limit`. |
| `pre_index` | string | — | Symbol to pre-index (narrow file set before scanning). |
| `pre_index_max_files` | int | `100` | Cap files from the probe. |
| `pre_index_include_parents` | int | `0` | Include N parent dirs of matched files. |
| `verbose` | bool | `false` | Verbose logging. |

**Returns:** `map` (string), `report` (dict), plus `token_estimate`,
`full_repo_estimate`, `savings_pct`, and a `tier_hint` advisory. With
`output_file`: `map_file`, `token_estimate`, `tier`, `format`, `report`.

---

## tricorder_detect

Search identifiers by name — the cheapest way to locate a known symbol.

| Param | Type | Default | Description |
|---|---|---|---|
| `project_root` | string | — | **Required.** Absolute path. |
| `query` | string | — | **Required.** Identifier to find. |
| `max_results` | int | `50` | Max results. |
| `context_lines` | int | `2` | Source lines around each hit. |
| `include_definitions` | bool | `true` | Include definition occurrences. |
| `include_references` | bool | `true` | Include reference occurrences. |
| `search_mode` | string | `"substring"` | `"exact"` (whole word), `"substring"` (contains), `"regex"` (Python regex). Case-insensitive for exact/substring. |
| `pre_index` / `pre_index_max_files` / `pre_index_include_parents` | | | Same as `tricorder_scan`. |

**Returns:** list of hits — file, line, def/ref kind, name, context lines.
Use `search_mode: "exact"` when `"map"` matching `"mapping"`/`"bitmap"` is noise.

---

## tricorder_symbols

Structured symbol query with type + file filters. Returns full records.

| Param | Type | Default | Description |
|---|---|---|---|
| `project_root` | string | — | **Required.** Absolute path. |
| `query` | string | `""` | Case-insensitive substring match on symbol name. Empty matches all. |
| `type` | string | — | Filter by symbol type: `function`, `class`, `type`, `variable`, `method`, `import`. Exact match. |
| `file` | string | — | Filter by file path (substring). |
| `limit` | int | `50` | Max results (caps at 200). |

**Returns:** records with `name`, `type`, `file`, line range, `signature`,
`docstring`, `language`, tree-sitter kind. Note: Python method names are
returned bare (`render`) while the repo map shows them qualified
(`Renderer::render`) — both resolve to the same symbol; see
[class-context-qualification](class-context-qualification.md).

---

## tricorder_detail

Deep-dive on one symbol: full body plus its callers and callees.

| Param | Type | Default | Description |
|---|---|---|---|
| `project_root` | string | — | **Required.** Absolute path. |
| `file` | string | — | **Required.** File containing the symbol (relative to root). |
| `name` | string | — | **Required.** Symbol name. |
| `line` | int | `0` | Line number to disambiguate (optional). |
| `max_tokens` | int | — | Optional token budget for the response. Trims body, then callees, then callers (never identity/signature). Adds `"truncated": true`. Best-effort below the metadata floor. |

**Returns:** the symbol record with `body`, `callers`, `callees`. Name matching
is exact on the base name first, then fuzzy (substring, `::`-aware) — a symbol
found via `tricorder_detect` will always resolve here even if the scope
differs.

---

## tricorder_query

Graph traversal DSL over the call graph. Replaces 5+ detect/detail round-trips
with one query.

| Param | Type | Default | Description |
|---|---|---|---|
| `project_root` | string | — | **Required.** Absolute path. |
| `query` | string | — | **Required.** Traversal expression (below). |
| `token_limit` | int | `2048` | Max tokens for the response. |

**Grammar:**

```
query      := traversal ('|' traversal)*
traversal  := kind '(' target ')' modifiers?
kind       := callers | callees | refs | tests_for
modifiers  := depth=N | exclude=GLOB | include=GLOB
              | type=function|class|method|variable | limit=N
```

**Examples:**

```
callers('authenticate') depth=2
callees('main') depth=1 exclude=tests/**
refs('Config') type=class limit=50
callers('foo') | callees('bar') depth=3
```

**Returns:** `{nodes, edges, token_estimate, savings_pct}` — the subgraph as
node/edge lists, sized to `token_limit`.

`tests_for('symbol')` behaves like `callers` but only follows references from
recognized test files (`tests/`, `test_*`, `*_test.*`, `*.test.*`,
`*_spec.*`, `__tests__/`) and labels those edges `tests` — "what tests cover
this symbol?"

---

## tricorder_diff

What changed since the last scan. Read-only; compares working-tree file
fingerprints against the scan index.

| Param | Type | Default | Description |
|---|---|---|---|
| `project_root` | string | — | **Required.** Absolute path. |

**Returns:** `{added, modified, deleted, tags, indexed}` — sorted path lists
plus parsed tags for added/modified files. When no index exists every
discovered file is reported as `added` and `indexed` is `false`.

---

## tricorder_locate

One-call auto-escalation: runs detect, then details the best match. Collapses
the usual find-the-symbol → show-it flow into a single round trip.

| Param | Type | Default | Description |
|---|---|---|---|
| `project_root` | string | — | **Required.** Absolute path. |
| `query` | string | — | **Required.** Symbol name to locate. |
| `max_tokens` | int | `2048` | Token budget for the matched detail (best-effort; metadata always survives). |
| `max_alternatives` | int | `5` | Max alternative candidates listed for disambiguation. |

**Returns:** `{query, match, alternatives, truncated?}` — `match` is the best
match's full detail (exact-name definition preferred; fuzzy rescue used only
when nothing exact matched), `alternatives` are the other candidates as
`{name, file, line, kind, quality}`. `match` is `None` with a `note` when
nothing is found.

---

## The escalation ladder

The bundled skill teaches this order — stop at the first rung that answers
the question:

1. **`tricorder_scan`** (map, ~14 tokens/tag) — "where is the auth code?"
2. **`tricorder_detect`** (~1–2 tokens/tag) — "where is `authenticate` defined?"
3. **`tricorder_detail`** (~50–400 tokens) — "what does it do, who calls it?"
4. **`tricorder_scan` tier=1** (~350 tokens/tag) — "show me the shape of this subsystem"
5. **Read the file** (last resort) — full source when necessary

Shortcuts: **`tricorder_locate`** collapses rungs 2–3 into one call
("find it and show it"), and **`tricorder_diff`** answers "what changed since
the last scan?" without re-scanning.
