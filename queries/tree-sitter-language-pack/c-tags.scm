(struct_specifier name: (type_identifier) @name.definition.class body:(_)) @definition.class

(declaration type: (union_specifier name: (type_identifier) @name.definition.class)) @definition.class

(function_declarator declarator: (identifier) @name.definition.function) @definition.function

(type_definition declarator: (type_identifier) @name.definition.type) @definition.type

(enum_specifier name: (type_identifier) @name.definition.type) @definition.type

; References

(call_expression function: (identifier) @name.reference.function) @reference.call

(call_expression
  function: (field_expression
    field: (field_identifier) @name.reference.function)) @reference.call

(declaration type: (type_identifier) @name.reference.type) @reference.type

(declaration type: (struct_specifier name: (type_identifier) @name.reference.type)) @reference.type

(declaration type: (union_specifier name: (type_identifier) @name.reference.type)) @reference.type

(declaration type: (enum_specifier name: (type_identifier) @name.reference.type)) @reference.type

(parameter_declaration type: (type_identifier) @name.reference.type) @reference.type

(cast_expression type: (type_descriptor) @name.reference.type) @reference.type
