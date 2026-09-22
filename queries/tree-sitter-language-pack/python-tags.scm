(module (expression_statement (assignment left: (identifier) @name.definition.constant) @definition.constant))
; Module-level assignments parse as direct children (no expression_statement wrapper)
(module (assignment left: (identifier) @name.definition.constant) @definition.constant)

(class_definition
  name: (identifier) @name.definition.class) @definition.class

(function_definition
  name: (identifier) @name.definition.function) @definition.function

(call
  function: [
      (identifier) @name.reference.call
      (attribute
        attribute: (identifier) @name.reference.call)
  ]) @reference.call

; Bare identifiers in call-argument position (positional or keyword
; value): `handlers.setdefault(HTTPException, http_exception_handler)`
; registers the handler without calling it, so call-target-only refs
; make the registration site invisible to detect/symbols/detail.
; Attribute values (obj.attr) and splats stay untagged — narrow on
; purpose: every extra ref kind multiplies DB rows and caller noise.
(call
  arguments: (argument_list
    (identifier) @name.reference.argument))
(call
  arguments: (argument_list
    (keyword_argument
      value: (identifier) @name.reference.argument)))
