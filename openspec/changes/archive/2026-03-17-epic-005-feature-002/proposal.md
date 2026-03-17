# Expand Path Parser and Batch Fetcher Implementation

## Goal
Expand Path Parser and Batch Fetcher Implementation: Develop the expand path parser, batch fetcher, cycle detector, and max_size enforcer for efficient data fetching and validation.

## Acceptance Criteria
- Given a complex expand path with multiple nested fields like "user.profile.settings", when the parser processes it, then it correctly identifies all referenced fields and their relationships including parent-child associations
- Given an expansion path with multiple entity references such as "orders.items.product", when the batch fetcher executes, then it performs only one database query per list instead of N individual queries for each entity type
- Given an expansion path contains circular references like "user.orders.items.user", when validation occurs, then it detects cycles and throws a CycleDetectionError with specific error message indicating the cycle path
- Given an expansion path exceeds maximum allowed size configured as 100 characters, when the parser processes it, then it throws a MaxSizeExceededError with clear error message specifying the limit and actual size
- Given a simple expansion path like "user.name", when the batch fetcher executes, then it correctly fetches the referenced fields in single database query without any batching
- Given multiple nested levels with same field names like "user.profile.settings.name" and "user.settings.name", when the parser processes it, then it correctly resolves field uniqueness and hierarchy
- Given a malformed expansion path such as "user..profile", when the parser processes it, then it throws a ParsingError with descriptive error message indicating invalid syntax
- Given a valid expansion path like "user.orders.items.product", when the cycle detector executes, then it correctly identifies no cycles and allows query execution to proceed
- Given an expansion path with maximum allowed size exactly at limit, when the parser processes it, then it successfully validates without throwing MaxSizeExceededError
- Given a complex expansion path that spans multiple entities and nested fields such as "user.orders.items.product.category", when the batch fetcher executes, then it performs optimized database queries with appropriate joins or separate queries based on entity relationships

## Constraints
- Complexity: high
