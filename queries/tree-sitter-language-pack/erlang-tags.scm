; Definitions (parent @definition.* + name @name.definition.* pairs —
; get_symbols pairs them positionally for end_line/body)

; module name: -module(sample).
(module_attribute
  (atom) @name.definition.module) @definition.module

; function name: each clause head (multi-clause = one tag per clause)
(function_clause
  (atom) @name.definition.function) @definition.function

; record name: -record(state, {...}).
(record_decl
  (atom) @name.definition.record) @definition.record

; macro name: -define(TIMEOUT, ...).
(pp_define
  (macro_lhs) @name.definition.macro) @definition.macro

; References

; local call: helper(1)
(call
  (atom) @name.reference.call)

; remote call mod:remote(X) — inner (call (atom)) matches too
