(struct_specifier name: (type_identifier) @name.definition.class body: (_)) @definition.class

(declaration type: (union_specifier name: (type_identifier) @name.definition.class)) @definition.class

(function_declarator declarator: (identifier) @name.definition.function) @definition.function

(function_declarator declarator: (field_identifier) @name.definition.function) @definition.function

(function_declarator declarator: (qualified_identifier scope: (namespace_identifier) @local.scope name: (identifier) @name.definition.method)) @definition.method

(type_definition declarator: (type_identifier) @name.definition.type) @definition.type

(enum_specifier name: (type_identifier) @name.definition.type) @definition.type

(class_specifier name: (type_identifier) @name.definition.class) @definition.class

; --- References ---
; Function/method calls via field access: obj.method()
(call_expression
  function: (field_expression
    field: (field_identifier) @name.reference.call)) @reference.call

; Function/method calls via qualified name: ns::func()
(call_expression
  function: (qualified_identifier
    name: (identifier) @name.reference.call)) @reference.call

; Free function calls: func()
(call_expression
  function: (identifier) @name.reference.call) @reference.call

; Type usage in declarations: PresetState state;
; Catches free-standing declarations (PresetState state; in function body)
(declaration
  type: (type_identifier) @name.reference.class) @reference.class

; Type usage in field declarations: PresetState state; (class member)
(field_declaration
  type: (type_identifier) @name.reference.class) @reference.class

; Type usage in function parameters: void Draw(const PresetState& state)
(parameter_declaration
  type: (type_identifier) @name.reference.class) @reference.class

; Template arguments: make_shared<PresetState>
(template_argument_list
  (type_identifier) @name.reference.class) @reference.class

; Qualified type usage in declarations: libprojectM::PresetState s;
(declaration
  type: (qualified_identifier
    name: (type_identifier) @name.reference.class)) @reference.class

; Qualified type usage in fields: libprojectM::PresetState s;
(field_declaration
  type: (qualified_identifier
    name: (type_identifier) @name.reference.class)) @reference.class

; Qualified type usage in params: void f(const ns::PresetState& s)
(parameter_declaration
  type: (qualified_identifier
    name: (type_identifier) @name.reference.class)) @reference.class
