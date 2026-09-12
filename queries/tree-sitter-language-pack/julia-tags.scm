; Definitions (paired captures for get_symbols)

(function_definition
  (signature
    (call_expression
      (identifier) @name.definition.function))) @definition.function

; References (the def-site signature also matches; same-line def+ref
; pairs are harmless — edges require different files)

(call_expression
  (identifier) @name.reference.call)
