# CEL Context Construction with Type Coercion

## Goal
CEL Context Construction with Type Coercion: Implement the construction of evaluation contexts that merge entity maps, existing maps, expanded fields, and handle type coercion.

## Acceptance Criteria
- Given entity data with mixed field types including strings, numbers, booleans, and nested objects, when building the context, then it correctly merges data from different sources maintaining type integrity for each field
- Given a field requires type conversion during context construction where a string field contains numeric data, when the context is built, then it properly coerces values from string to number type
- Given a field requires type conversion during context construction where a numeric field contains boolean data, when the context is built, then it properly coerces values from number to boolean type
- Given conflicting field values from multiple maps where one map has a field "status" with value "active" and another has "status" with value "inactive", when the context constructs, then it follows defined precedence rules resolving conflicts with the last map's value taking priority
- Given conflicting field values from multiple maps where a nested object field "user.profile" exists in both maps, when the context constructs, then it merges nested objects recursively while maintaining type integrity for each nested field
- Given an entity map with missing fields that are required during context construction, when the context is built, then it properly handles missing fields by using default values or null values as specified in configuration
- Given a field requiring conversion from string to boolean where the string value is "true", when the context is built, then it correctly coerces the value to boolean true
- Given a field requiring conversion from string to boolean where the string value is "false", when the context is built, then it correctly coerces the value to boolean false
- Given a field requiring conversion from numeric to string where the number is 42, when the context is built, then it correctly coerces the value to string "42"
- Given multiple maps with overlapping fields and varying data types, when the context constructs, then it follows a defined type precedence order (string > number > boolean > null) for resolving conflicts

## Constraints
- Complexity: medium
