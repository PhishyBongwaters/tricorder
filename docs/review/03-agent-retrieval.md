# Agent retrieval — how agents pull answers out of a scan

Source of truth: the code. Every claim below names its file.

Agents don't read the DB directly. They get five MCP tools
(`tricorder_server.py`) plus a turn-0 injection that orients them before
they ask anything. The designed order is cheapest-first: locate, shape,
body, graph, map. Stop at the first rung that answers.

## 1. The five tools

| tool | question it answers | costs |
|---|---|---|
| `tricorder_detect` | where is this identifier? (file, line, context) | cheapest |
| `tricorder_symbols` | what is its shape? (type, range, signature, docstring) | cheap |
| `tricorder_detail` | show me the body + its callers/callees | medium |
| `tricorder_query` | traverse the graph (callers/callees/refs/defs, piped, depth-limited) | medium |
| `tricorder_scan` | give me the ranked map (or write it to disk) | most expensive |

Before asserting or editing anything found this way, open the exact file
lines. The map navigates; the file is truth.

### detect / symbols — deterministic matching with a safety net

Exact → substring → regex (`tricorder_detect`, `tricorder_server.py:696`;
`tricorder_symbols`, `:890`), then the retrieve-0 rescue over
orthographic variants: template args, parens, and namespace qualifiers
stripped, word parts re-joined under every separator/case form,
single-word verb synonyms (`get/fetch/load…`), and finally an
edit-distance + token-overlap pass for typos and affixes
(`_query_variants`, `_levenshtein`, `_tokenize`,
`tricorder_server.py:36-140`). Rescue hits are flagged
`quality: "fuzzy"` — lookalikes, not exact hits, verify in source.
No ML, no model calls, reproducible.

### escalation hints — the ladder, machine-readable

Empty results (even after rescue) and fuzzy rescues return an
`escalation: {next_rung, reason, evidence, message}` object
(`_escalation_hint`, `tricorder_server.py:106-141`). Empty detect →
try symbols; empty symbols → try query; any fuzzy hit → verify via
detail. A fixed decision table over already-computed signals, never
content judgment.

### detail — body plus both directions

`tricorder_detail(project_root, file, name, line)`
(`tricorder_server.py:1017`): the symbol record plus `body` (first 500
chars), in-file and cross-file `callers`/`callees`, restored from the
cross-ref bundle without re-parsing (`graph.py:44-100`). Not found →
`{"error": "not found"}`, exit 0.

### query — one call instead of five round-trips

`tricorder_query(project_root, query, token_limit=2048)`
(`tricorder_server.py:1081`). DSL: `callers('x')`, `callees('x')`,
`refs('x')`, `defs('x')`, chained with `|`, modifiers `depth=`,
`exclude=`/`include=` globs, `type=`, `limit=`. Parsed by a hand-rolled
parser (`utils.parse_query_dsl`, no grammar dependency), executed by
`Tricorder.query_graph` (`graph.py:246`) as BFS over the cross-file
index. Unknown names return `symbol_not_found`, not an empty guess.

### scan — the map, budgeted

`tricorder_scan` (`tricorder_server.py:365`) is the full map builder with
agent-oriented guards: `token_limit` truncation, `tier` 0/1 cost control,
`output_file` (write the map to disk, return only the path — mandatory
hygiene past ~50 files), `dry_run` (price the map before buying it),
`exclude_globs` for vendored subtrees, and `tier_hint` when the budget
truncated the tag set (`tricorder_server.py:567,633`). Every response
carries `token_estimate`, `full_repo_estimate`, `savings_pct`
(`_budget_fields`, `tricorder_server.py:315`) — the agent always knows
what it spent and what it saved.

## 2. Turn-0 injection — orientation before questions

A fresh session with the repo as root gets one of:

- the DB digest (mapped repos): what the map covers, what it cost;
- the probe digest (unmapped repos): cheap language/file tally plus a
  navigation hint, no map built (`utils.py:737+`, shared by CLI
  `--probe-digest`, the Hermes plugin, and the DSH plugin).

Three carriers, same payload: `tricorder_client.inject_turn0_map`
(`tricorder_client.py:319`), `tricorder_inject.TricorderInjector`
(`tricorder_inject.py:90`), and the Hermes plugin
(`plugins/tricorder/__init__.py`), which shells the CLI with `--db-path`
pointed at the canonical in-repo DB — so a slash scan, the MCP tools,
and `chunk_resume.py` all read and write the same sqlite.

## 3. Narrowing giant trees without walking them

`--pre-index SYMBOL` (CLI) / `pre_index` (MCP): find which files mention
a symbol first (ctags index if built, else `rg`), then restrict the
scan to those files plus N parent dirs
(`ctags_probe.probe_and_narrow`, `ctags_probe.py:444`). The guards that
matter: index builds refuse trees over 20,000 files, existing tag files
over 100MB are never read, and `rg` substring search is the primary
fast path — no index needed, sub-second on huge trees.
