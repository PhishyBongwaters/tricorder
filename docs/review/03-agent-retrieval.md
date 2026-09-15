# Agent retrieval — the MCP tools and turn-0 injection

Source of truth: the code. Every claim below names its file.

Agents do not read the DB directly. They get five MCP tools
(`tricorder_server.py`) plus a turn-0 injection that orients a fresh
session before it asks anything. Listed below in ascending order of
response cost.

## 1. The five tools

| tool | returns | cost |
|---|---|---|
| `tricorder_detect` | identifier locations: file, line, context | lowest |
| `tricorder_symbols` | symbol shape: type, range, signature, docstring | low |
| `tricorder_detail` | body plus callers and callees | medium |
| `tricorder_query` | graph traversal (callers/callees/refs/defs, piped) | medium |
| `tricorder_scan` | the ranked map, inline or to disk | highest |

### detect / symbols

Deterministic matching: exact, substring, then regex
(`tricorder_detect`, `tricorder_server.py:696`;
`tricorder_symbols`, `:890`), followed by the retrieve-0 rescue over
orthographic variants — template arguments, parens, and namespace
qualifiers stripped; word parts re-joined under every
separator/case form; single-word verb synonyms; then an
edit-distance and token-overlap pass
(`_query_variants`, `_levenshtein`, `_tokenize`,
`tricorder_server.py:36-140`). Rescue hits carry
`quality: "fuzzy"`: lookalikes, not exact hits. No ML, no model
calls.

### escalation hints

Empty results (even after rescue) and fuzzy rescues return
`escalation: {next_rung, reason, evidence, message}`
(`_escalation_hint`, `tricorder_server.py:106-141`): a fixed decision
table over already-computed signals. Empty detect names symbols as
the next rung; empty symbols names query; any fuzzy hit names detail
with a verify-before-use message.

### detail

`tricorder_detail(project_root, file, name, line)`
(`tricorder_server.py:1017`): the symbol record plus `body` (first
500 chars) and in-file plus cross-file `callers`/`callees`, restored
from the cross-ref bundle without re-parsing (`graph.py:44-100`).
Unknown symbols return `{"error": "not found"}` with exit code 0.

### query

`tricorder_query(project_root, query, token_limit=2048)`
(`tricorder_server.py:1081`). DSL: `callers('x')`, `callees('x')`,
`refs('x')`, `defs('x')`, chained with `|`, with `depth=`,
`exclude=`/`include=`, `type=`, and `limit=` modifiers. Parsed by a
hand-rolled parser (`utils.parse_query_dsl`) and executed by
`Tricorder.query_graph` (`graph.py:246`) as BFS over the cross-file
index. Unknown names return `symbol_not_found`.

### scan

`tricorder_scan` (`tricorder_server.py:365`): the full map builder.
`token_limit` truncates, `tier` selects definitions-only (0) or
definitions plus context lines (1), `output_file` writes the map to
disk and returns only the path (recommended past roughly 50 files),
`dry_run` prices the map without building it, `exclude_globs` cuts
vendored subtrees before ranking, and `tier_hint` reports when the
budget truncated the tag set (`tricorder_server.py:567,633`). Every
response carries `token_estimate`, `full_repo_estimate`, and
`savings_pct` (`_budget_fields`, `tricorder_server.py:315`).

## 2. Turn-0 injection

A fresh session with the repo as root receives one of:

- the DB digest (mapped repos): coverage and cost of the stored map;
- the probe digest (unmapped repos): language and file tally plus a
  navigation hint, with no map built and no token budget spent
  (`utils.py:737+`, shared by CLI `--probe-digest`, the Hermes
  plugin, and the DSH plugin).

Three carriers, one payload: `tricorder_client.inject_turn0_map`
(`tricorder_client.py:319`), `tricorder_inject.TricorderInjector`
(`tricorder_inject.py:90`), and the Hermes plugin
(`plugins/tricorder/__init__.py`), which shells the CLI with
`--db-path` pointed at the canonical in-repo DB — so slash scans,
MCP tools, and `chunk_resume.py` read and write the same sqlite.
Plugin and skill details: `05-plugins-and-skills.md`.

## 3. Narrowing without walking

`--pre-index SYMBOL` (CLI) / `pre_index` (MCP): find which files
mention a symbol first (ctags index when built, otherwise `rg`),
then restrict the scan to those files plus N parent directories
(`ctags_probe.probe_and_narrow`, `ctags_probe.py:444`). Index builds
refuse trees over 20,000 files; existing tag files over 100MB are
never read; `rg` substring search is the primary path.
