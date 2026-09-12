# Language expansion SPEC — the 51 grammar-only languages

Goal: a query for every language that has real definitions. Config and
data formats stay `no-query` on purpose — that is the correct answer
for them, not a gap.

## Triage (judgment, verify per language while working)

CODE — worth a query (25): bash, cairo, clojure, cmake, fortran, func,
gdscript, glsl, gn, groovy, hack, haskell, julia, llvm, make, matlab,
pascal, perl, powershell, proto, sql, svelte, tsx, verilog, vue, wast,
wat, zig, uxntal, tablegen.

CONFIG/DATA — `no-query` is correct (21): comment, css, csv,
dockerfile, git_config, gitattributes, gitcommit, gitignore, gomod,
gosum, html, ini, jsdoc, json, latex, markdown, pymanifest,
requirements, toml, yaml.

(Neither triage list is gospel — the probe decides. If the grammar has
no definition-like nodes, the language moves to config regardless of
this table.)

## Per-language work order (each: probe → query → matrix → green)

For each CODE language:

1. `filename_to_lang` check — if no extension maps (ql lesson), it
   goes back to unproven regardless of grammar.
2. AST dump of a minimal sample; identify def/call shapes.
3. `<lang>-tags.scm` in `queries/tree-sitter-language-pack/` with
   **paired** captures (`@definition.X` parent + `@name.definition.X`
   name — name-only yields tags but zero symbol records).
4. `scm.py` map entry + `WIDER_LANGUAGE_PACK` sample.
5. Matrix green → move to validated in `06-languages.md`.

## Status

| Batch | Languages | State |
|---|---|---|
| 1 | bash, powershell, perl, haskell, julia | done (36 subtests green) |
| 2 | zig, verilog, groovy, hack, pascal | done (41 subtests green) |
| 3 | matlab, fortran, clojure, gdscript, cairo | done (46 subtests green) |
| 4 | sql, proto, make, cmake (gn excluded: target names are strings) | done (50 green) |
| 5 | glsl, func, tsx (svelte/vue excluded: script blocks are raw_text) | done (53 green) |
| 6 | uxntal, llvm, tablegen (wast/wat unreachable: no ext mapping) | done (56 green) |

All six batches complete. Remaining unproven: hcl (weak query),
properties/udev (config formats), ql/wast/wat (no ext mapping),
gn/svelte/vue (nothing taggable). Config/data formats stay `no-query`
by design.

## Backlog — next languages (probed Sep 2026)

Tier A — DONE (16/16, matrix green): actionscript, ada, fish, hare,
haxe, janet, nix, odin, qmljs, scheme, starlark, tcl, thrift, vhdl,
vim, wgsl.

Tier B — needs ext mapping first (grammar live, no extension maps):
nim (.nim), fsharp (.fs — collides with forth, needs care), vb
(.vb), mojo (.mojo), crystal (.cr), awk (.awk), cython (.pyx),
smalltalk (.st), sml (.sml), vala (.vala), v (.v — collides with
verilog, needs care), graphql (.graphql), lean (.lean), ql (.ql),
wast (.wast), wat (.wat). Fix lives in OUR `detect_lang`
(`utils.py` wraps grep-ast): a local ext→lang table checked before
`filename_to_lang`. Then Tier A path.

Already covered by alias (no work): zsh → bash query, systemverilog
→ verilog query, wgsl_bevy → wgsl (once written), terraform → hcl
(weak, see hcl note).

Upstream-only (no grammar in pack): futhark, xq, embeddedtemplate.

Known mis-mapping (do not touch without a plan): `.m` → matlab,
so Objective-C files parse as Matlab. Disambiguation needs content
sniffing; both languages claim the extension.

Batches ordered by likely value (scripting + systems languages first,
niche DSLs last). Update this table as batches land.
