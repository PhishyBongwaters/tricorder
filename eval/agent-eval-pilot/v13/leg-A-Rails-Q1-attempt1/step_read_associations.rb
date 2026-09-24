1421:         #   has_many :subscribers, through: :subscriptions, source: :user
1422:         #   has_many :subscribers, through: :subscriptions, disable_joins: true
1423:         #   has_many :comments, strict_loading: true
1424:         #   has_many :comments, query_constraints: [:blog_id, :post_id]
1425:         #   has_many :comments, index_errors: :nested_attributes_order
1426:         def has_many(name, scope = nil, **options, &extension)
1427:           reflection = Builder::HasMany.build(self, name, scope, options, &extension)
1428:           Reflection.add_reflection(self, name, reflection)
1429:         end
1430: 
1431:         # Specifies a one-to-one association with another class. This method
1432:         # should only be used if the other class contains the foreign key. If
1433:         # the current class contains the foreign key, then you should use
1434:         # #belongs_to instead. See {Is it a belongs_to or has_one
1435:         # association?}[rdoc-ref:Associations::ClassMethods@Is+it+a+-23belongs_to+or+-23has_one+association-3F]
1436:         # for more detail on when to use #has_one and when to use #belongs_to.
1437:         #
1438:         # The following methods for retrieval and query of a single associated object will be added:
1439:         #
1440:         # +association+ is a placeholder for the symbol passed as the +name+ argument, so
