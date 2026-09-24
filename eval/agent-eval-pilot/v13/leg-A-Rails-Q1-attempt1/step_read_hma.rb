1: # frozen_string_literal: true
2: 
3: module ActiveRecord
4:   module Associations
5:     # = Active Record Has Many Association
6:     #
7:     # This is the proxy that handles a has many association.
8:     #
9:     # If the association has a <tt>:through</tt> option further specialization
10:     # is provided by its child HasManyThroughAssociation.
11:     class HasManyAssociation < CollectionAssociation # :nodoc:
12:       include ForeignAssociation
13: 
14:       def handle_dependency
15:         case options[:dependent]
16:         when :restrict_with_exception
17:           raise ActiveRecord::DeleteRestrictionError.new(reflection.name) unless empty?
18: 
19:         when :restrict_with_error
20:           unless empty?
21:             record = owner.class.human_attribute_name(reflection.name).downcase
22:             owner.errors.add(:base, :'restrict_dependent_destroy.has_many', record: record)
23:             throw(:abort)
24:           end
25: 
26:         when :destroy
27:           # No point in executing the counter update since we're going to destroy the parent anyway
28:           load_target.each { |t| t.destroyed_by_association = reflection }
29:           destroy_all
30:         when :destroy_async
31:           load_target.each do |t|
32:             t.destroyed_by_association = reflection
33:           end
34: 
35:           unless target.empty?
36:             association_class = target.first.class
37:             if association_class.query_constraints_list
38:               primary_key_column = association_class.query_constraints_list
39:               ids = target.collect { |assoc| primary_key_column.map { |col| assoc.public_send(col) } }
40:             else
41:               primary_key_column = association_class.primary_key
42:               ids = target.collect { |assoc| assoc.public_send(primary_key_column) }
43:             end
44: 
45:             ids.each_slice(owner.class.destroy_association_async_batch_size || ids.size) do |ids_batch|
46:               enqueue_destroy_association(
47:                 owner_model_name: owner.class.to_s,
48:                 owner_id: owner.id,
49:                 association_class: reflection.klass.to_s,
50:                 association_ids: ids_batch,
51:                 association_primary_key_column: primary_key_column,
52:                 ensuring_owner_was_method: options.fetch(:ensuring_owner_was, nil)
53:               )
54:             end
55:           end
56:         else
57:           delete_all
58:         end
59:       end
60: 
61:       def insert_record(record, validate = true, raise = false)
62:         set_owner_attributes(record)
63:         super
64:       end
65: 
66:       private
67:         # Returns the number of records in this collection.
68:         #
69:         # If the association has a counter cache it gets that value. Otherwise
70:         # it will attempt to do a count via SQL, bounded to <tt>:limit</tt> if
71:         # there's one. Some configuration options like :group make it impossible
72:         # to do an SQL count, in those cases the array count will be used.
73:         #
74:         # That does not depend on whether the collection has already been loaded
75:         # or not. The +size+ method is the one that takes the loaded flag into
76:         # account and delegates to +count_records+ if needed.
77:         #
78:         # If the collection is empty the target is set to an empty array and
79:         # the loaded flag is set to true as well.
80:         def count_records
81:           count = if reflection.has_active_cached_counter?
82:             owner.read_attribute(reflection.counter_cache_column).to_i
83:           else
84:             scope.count(:all)
85:           end
86: 
87:           # If there's nothing in the database, @target should only contain new
88:           # records or be an empty array. This is a documented side-effect of
89:           # the method that may avoid an extra SELECT.
90:           if count == 0
91:             target.select!(&:new_record?)
92:             loaded!
93:           end
94: 
95:           [association_scope.limit_value, count].compact.min
96:         end
97: 
98:         def update_counter(difference, reflection = reflection())
99:           if reflection.has_cached_counter?
100:             owner.increment!(reflection.counter_cache_column, difference)
