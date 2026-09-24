91:     #   has_many :comments
92:     # end
93:     #
94:     # Post.first.comments and Post.first.comments= methods are defined by this method...
95:     def self.define_accessors(model, reflection)
96:       mixin = model.generated_association_methods
97:       name = reflection.name
98:       define_readers(mixin, name)
99:       define_writers(mixin, name)
100:     end
101: 
102:     def self.define_readers(mixin, name)
103:       mixin.class_eval <<-CODE, __FILE__, __LINE__ + 1
104:         def #{name}
105:           association = association(:#{name})
106:           deprecated_associations_api_guard(association, __method__)
107:           association.reader
108:         end
109:       CODE
110:     end
111: 
112:     def self.define_writers(mixin, name)
113:       mixin.class_eval <<-CODE, __FILE__, __LINE__ + 1
114:         def #{name}=(value)
115:           association = association(:#{name})
116:           deprecated_associations_api_guard(association, __method__)
117:           association.writer(value)
118:         end
119:       CODE
120:     end
121: 
122:     def self.define_validations(model, reflection)
123:       # noop
124:     end
125: 
126:     def self.define_change_tracking_methods(model, reflection)
127:       # noop
128:     end
129: 
130:     def self.valid_dependent_options
