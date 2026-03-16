## 1. Core Context Construction

- [x] 1.1 Enhance ValidationContext constructor to accept entity_maps parameter (list of dicts)
- [x] 1.2 Implement _merge_maps() method with last-map-wins for scalar values
- [x] 1.3 Implement _deep_merge() for recursive nested object merging
- [x] 1.4 Add support for expanded fields via dot-notation in entity data

## 2. Type Coercion

- [x] 2.1 Add type coercion utilities module (src/hippo/core/validators/coerce.py)
- [x] 2.2 Implement coerce_to_number() - string to int/float
- [x] 2.3 Implement coerce_to_boolean() - string "true"/"false" to bool, number to bool
- [x] 2.4 Implement coerce_to_string() - number to string
- [x] 2.5 Implement get_type_precedence() returning (string: 4, number: 3, boolean: 2, null: 1)
- [x] 2.6 Add type_coercion_enabled parameter to ValidationContext
- [x] 2.7 Apply type coercion during map merging when enabled

## 3. Missing Field Handling

- [x] 3.1 Add default_values parameter to ValidationContext constructor
- [x] 3.2 Implement get_field_with_default() method
- [x] 3.3 Return null for missing fields without defaults

## 4. Context API Enhancements

- [x] 4.1 Add get_merged_context() method returning the final merged dict
- [x] 4.2 Add get_field(path: str) method with dot-notation support
- [x] 4.3 Add get_coercion_warnings() method returning list of coercion events for logging

## 5. Testing

- [x] 5.1 Write unit tests for _merge_maps() with scalar conflicts
- [x] 5.2 Write unit tests for _deep_merge() nested objects
- [x] 5.3 Write unit tests for type coercion (string→number, number→boolean, string→boolean, number→string)
- [x] 5.4 Write unit tests for type precedence order
- [x] 5.5 Write unit tests for missing field handling with defaults
- [x] 5.6 Write integration tests for ValidationContext with all features combined
- [x] 5.7 Run existing tests to ensure backward compatibility
