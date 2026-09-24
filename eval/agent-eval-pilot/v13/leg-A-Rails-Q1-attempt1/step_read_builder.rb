1: # frozen_string_literal: true
2: 
3: module ActiveRecord::Associations::Builder # :nodoc:
4:   class HasMany < CollectionAssociation # :nodoc:
5:     def self.macro
6:       :has_many
7:     end
8: 
9:     def self.valid_options(options)
10:       valid = super + [:counter_cache, :join_table, :index_errors, :default_order, :as, :through]
11:       valid += [:foreign_type] if options[:as]
12:       valid += [:source, :source_type, :disable_joins] if options[:through]
13:       valid += [:ensuring_owner_was] if options[:dependent] == :destroy_async
14:       valid
15:     end
16: 
17:     def self.valid_dependent_options
18:       [:destroy, :delete_all, :nullify, :restrict_with_error, :restrict_with_exception, :destroy_async]
19:     end
20: 
21:     private_class_method :macro, :valid_options, :valid_dependent_options
22:   end
23: end
