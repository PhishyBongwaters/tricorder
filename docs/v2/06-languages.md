# Languages — validated, present, potential

Authority: `tests/test_language_matrix.py`. A language is **validated**
only if the matrix enforces it. Query files without matrix samples are
present, not proven.

## Validated (93, matrix-enforced)

Full signature: python, javascript, typescript, c, cpp, java, go,
rust, swift, csharp, ruby. Definition-only: kotlin, php, scala, dart,
elixir, ocaml, lua, commonlisp, erlang, arduino, chatito, d, elisp,
elm, gleam, ocaml_interface, pony, r, racket, solidity, bash,
powershell, perl, haskell, julia, zig, verilog, groovy, hack, pascal,
matlab, fortran, clojure, gdscript, cairo, sql, proto, make, cmake,
glsl, func, tsx, uxntal, llvm, tablegen, actionscript, ada, fish,
hare, haxe, janet, nix, odin, qmljs, scheme, starlark, tcl, thrift,
vhdl, vim, wgsl, nim, crystal, awk, cython, sml, vala, graphql,
lean, vb, fsharp, mojo, motoko, reason, rescript, sway, tact, yang,
yul, ql, wast, wat.

## Query present, not in matrix (3)

- hcl — extracts attribute junk as defs (weak query), not promotable
  as-is; needs a block-aware query rewrite.
- properties — extracts keys; config format, same class as below.
- udev — rule files have no definitions by nature; correctly
  unprovable.

## Potential (51, grammar but no query)

bash, cairo, clojure, cmake, css, dockerfile, fortran, gdscript, glsl,
html, json, latex, llvm, make, markdown,
matlab, proto, sql, svelte, toml, tsx,
vue, yaml, and the rest. The grammar parses; nothing
extracts tags, so these scan as `no-query`. (Non-code formats like
json/toml never need queries — `no-query` is correct for them.)

No grammar at all: embedded_template.

## Path to supported (per language)

1. Grammar check: `get_language('<key>')` must succeed (language-pack
   ships it). If not, stop — needs a new tree-sitter grammar upstream.
2. AST probe: parse a sample, dump node types. Find the
   definition/call shapes (see how `erlang-tags.scm` was built from
   `fun_decl`/`call` dumps).
3. Query: add `<lang>-tags.scm` under
   `queries/tree-sitter-language-pack/` with **paired** captures —
   `@definition.X` on the parent node + `@name.definition.X` on the
   identifier (`get_symbols` pairs them positionally; name-only
   captures yield tags but zero symbol records). Add the lang key to
   `scm.py`.
4. Matrix sample: append to `WIDER_LANGUAGE_PACK` (or `CLAIMED` with a
   signature). Green matrix = validated. Move the language up a tier
   in this doc.

## Refresh note

Files scanned while a language was `no-query` stay cache-hits after
support lands (size+mtime unchanged) — rescan with `--init --wipe`
to pick them up. Grammar support is a rescan-class change.
