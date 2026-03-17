## ADDED Requirements

### Requirement: Context merges data from multiple sources maintaining type integrity
Given entity data with mixed field types including strings, numbers, booleans, and nested objects, when building the context, then it correctly merges data from different sources maintaining type integrity for each field.

#### Scenario: Mixed field types are preserved
- **WHEN** context is constructed with entity data containing string "name", number age, boolean active, and nested object user
- **THEN** each field retains its original type in the merged context

#### Scenario: Multiple maps merge correctly
- **WHEN** context is constructed with entity_map_1 having field "a" and entity_map_2 having field "b"
- **THEN** the merged context contains both fields "a" and "b"

### Requirement: Context coerces string to number type
Given a field requires type conversion during context construction where a string field contains numeric data, when the context is built, then it properly coerces values from string to number type.

#### Scenario: String "123" coerces to number
- **WHEN** entity data contains field "count" with string value "123" and type coercion is enabled
- **THEN** the context returns number 123 for field "count"

#### Scenario: String "45.67" coerces to float
- **WHEN** entity data contains field "price" with string value "45.67" and type coercion is enabled
- **THEN** the context returns float 45.67 for field "price"

### Requirement: Context coerces number to boolean type
Given a field requires type conversion during context construction where a numeric field contains boolean data, when the context is built, then it properly coerces values from number to boolean type.

#### Scenario: Number 1 coerces to boolean true
- **WHEN** entity data contains field "enabled" with number value 1 and type coercion is enabled
- **THEN** the context returns boolean true for field "enabled"

#### Scenario: Number 0 coerces to boolean false
- **WHEN** entity data contains field "disabled" with number value 0 and type coercion is enabled
- **THEN** the context returns boolean false for field "disabled"

### Requirement: Context handles conflicting fields with precedence rules
Given conflicting field values from multiple maps where one map has a field "status" with value "active" and another has "status" with value "inactive", when the context constructs, then it follows defined precedence rules resolving conflicts with the last map's value taking priority.

#### Scenario: Last map wins for scalar conflicts
- **WHEN** entity_map_1 has field "status" = "active" and entity_map_2 has field "status" = "inactive"
- **THEN** the merged context has field "status" = "inactive"

### Requirement: Context merges nested objects recursively
Given conflicting field values from multiple maps where a nested object field "user.profile" exists in both maps, when the context constructs, then it merges nested objects recursively while maintaining type integrity for each nested field.

#### Scenario: Nested objects merge deeply
- **WHEN** entity_map_1 has {"user": {"name": "Alice", "age": 30}} and entity_map_2 has {"user": {"email": "alice@example.com"}}
- **THEN** the merged context has {"user": {"name": "Alice", "age": 30, "email": "alice@example.com"}}

#### Scenario: Nested scalar conflicts follow precedence
- **WHEN** entity_map_1 has {"user": {"name": "Alice"}} and entity_map_2 has {"user": {"name": "Bob"}}
- **THEN** the merged context has {"user": {"name": "Bob"}}

### Requirement: Context handles missing fields with defaults
Given an entity map with missing fields that are required during context construction, when the context is built, then it properly handles missing fields by using default values or null values as specified in configuration.

#### Scenario: Missing field returns null by default
- **WHEN** entity data does not contain field "optional_field"
- **THEN** accessing the field returns null

#### Scenario: Missing field uses configured default
- **WHEN** entity data does not contain field "count" and default value 0 is configured
- **THEN** accessing the field returns 0

### Requirement: Context coerces string "true"/"false" to boolean
Given a field requiring conversion from string to boolean where the string value is "true", when the context is built, then it correctly coerces the value to boolean true. Given a field requiring conversion from string to boolean where the string value is "false", when the context is built, then it correctly coerces the value to boolean false.

#### Scenario: String "true" coerces to boolean true
- **WHEN** entity data contains field "active" with string value "true" and type coercion is enabled
- **THEN** the context returns boolean true for field "active"

#### Scenario: String "false" coerces to boolean false
- **WHEN** entity data contains field "active" with string value "false" and type coercion is enabled
- **THEN** the context returns boolean false for field "active"

### Requirement: Context coerces number to string
Given a field requiring conversion from numeric to string where the number is 42, when the context is built, then it correctly coerces the value to string "42".

#### Scenario: Number 42 coerces to string "42"
- **WHEN** entity data contains field "id" with number value 42 and type coercion is enabled
- **THEN** the context returns string "42" for field "id"

### Requirement: Context follows type precedence order for conflicts
Given multiple maps with overlapping fields and varying data types, when the context constructs, then it follows a defined type precedence order (string > number > boolean > null) for resolving conflicts.

#### Scenario: String takes precedence over number
- **WHEN** entity_map_1 has field "value" = 123 (number) and entity_map_2 has field "value" = "456" (string)
- **THEN** the merged context has field "value" = "456" (string)

#### Scenario: Number takes precedence over boolean
- **WHEN** entity_map_1 has field "value" = true (boolean) and entity_map_2 has field "value" = 1 (number)
- **THEN** the merged context has field "value" = 1 (number)

#### Scenario: Boolean takes precedence over null
- **WHEN** entity_map_1 has field "value" = null and entity_map_2 has field "value" = true (boolean)
- **THEN** the merged context has field "value" = true (boolean)
