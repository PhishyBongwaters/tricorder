# Class-Context Qualification

How tricorder scopes method definitions as `Class::method`, and why the
sequential, incremental, and parallel scan paths all produce identical names.

## Problem

A repo map that lists bare `render` three times (one per class) is useless
to an agent. Method definitions need their enclosing class: `Renderer::render`.
Two mechanisms do this; they must agree everywhere.

## Mechanism 1 — Structural qualification (primary)

`parser.qualify_with_class_context(name, node, capture_name)` walks the
tree-sitter AST upward from the definition node and returns
`f"{nearest_class}::{name}"`.

- **Class-like node types** (`_CLASS_NODE_TYPES`): `class_declaration`,
  `struct_declaration`, `class_specifier`, `impl_item` (Rust), `class_definition`
  (Python). Innermost wins for nested classes.
- **Name child types** (`_CLASS_NAME_CHILD_TYPES`): `identifier`,
  `type_identifier`, `class_identifier`, `scoped_identifier`, `name`
  (tree-sitter-python nests the class name under `name`, not `identifier`).
- **Never re-qualifies**: names already containing `::` pass through untouched;
  class definitions themselves are exempt via `capture_name.endswith(".class")`
  (exact suffix, not substring — a future `class_method` capture can't false-match).

The helper is module-level, pure, and picklable — deliberately, so the
`ProcessPoolExecutor` fresh-scan worker (`ranking._parse_worker`) can call it
with no `self` and produce byte-identical names to the in-process path.

Applied in `ParserMixin.get_tags_raw` for every `def` tag, all languages.

## Mechanism 2 — Name heuristic (fallback)

For grammars with no mapped class node, `_add_class_context_to_tags`
(parser.py, operates on `Tag` objects) and `_apply_class_context_to_rows`
(ranking.py, operates on `(fname, rel_fname, line, name, kind)` tuples)
implement the legacy heuristic: an uppercase, paren-free `def` sets
`current_class`; subsequent `name(` defs get prefixed.

**Sync contract (issue #46):** the two implementations must stay behaviorally
identical. The worker can't call the mixin method (no `self`, must stay
picklable), so the heuristic is duplicated on tuples. Both carry the `::`
guard — structural qualification may already have scoped the name
(e.g. `Monitor::stretchMonitors()`), and it must never be qualified twice.
`tests/test_class_context.py` pins parity, including the no-double-qualify
regression.

## Staleness: EXTRACTOR_VERSION

`database.EXTRACTOR_VERSION` (currently 2) stamps every tag DB at write time.
`_get_ranked_tags_db()` compares the stored stamp: a mismatch means the
extractor changed since the DB was built, so stored tags are stale regardless
of file mtimes → force full rescan, re-stamp. Bump on **any** capture or
qualification change. Separate lineage from `cache.CACHE_VERSION` (query-time
bundles): a query-time fix must not force tag reparse, and vice versa.

## Deliberate asymmetry: tags vs symbols

`ParserMixin.get_symbols()` qualifies only C/C++/Rust names and leaves Python
symbols bare (`Renderer.render` stays `render`), while tag extraction qualifies
every language with `::`. This is intentional ("so Python stays dotted and
isn't mis-scoped"). Every consumer joins through `utils._base()`, substring,
or fuzzy matching:

- graph first-step lookup: exact key → `_base()` comparison fallback
- `get_symbol_details`: exact `_base()` → documented fuzzy fallback
- MCP `tricorder_detect`: case-insensitive substring + `::`-splitting rescue
- cross-file caller/callee index: always indexed by bare name

Do not "fix" the `get_symbols()` gate to qualify Python without auditing all
four joins — the asymmetry is load-bearing, not an oversight.

## Tests

- `tests/test_class_context.py` — 9 tests: structural qualification per
  language, nesting (innermost wins), `::` idempotence, class-definition
  exemption, heuristic parity, no-double-qualify regression.
- `tests/test_db_invariants.py` — extractor-version staleness behavior.
