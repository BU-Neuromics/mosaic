## 1. Core Implementation

- [x] 1.1 Create SchemaValidator class in hippo/core/validation/
- [x] 1.2 Implement ValidationResult dataclass with is_valid, errors, entity_id fields
- [x] 1.3 Implement required field validation logic
- [x] 1.4 Implement type constraint validation (string, number, boolean, timestamp)
- [x] 1.5 Implement enum validation logic
- [x] 1.6 Implement reference existence validation logic
- [x] 1.7 Implement nested field validation with dot-notation path support

## 2. Integration

- [x] 2.1 Add validate() method to IngestionPipeline pre-commit hook
- [x] 2.2 Wire ValidationResult into write operation response
- [x] 2.3 Configure validation to run before schema compilation in pipeline

## 3. Error Handling

- [x] 3.1 Implement error message formatting per spec patterns
- [x] 3.2 Implement multiple error collection in single ValidationResult
- [x] 3.3 Add nested field path formatting ("nested.field")

## 4. Testing

- [x] 4.1 Write unit test for missing required field scenario
- [x] 4.2 Write unit test for invalid string type scenario
- [x] 4.3 Write unit test for invalid number type scenario
- [x] 4.4 Write unit test for invalid boolean type scenario
- [x] 4.5 Write unit test for invalid timestamp format scenario
- [x] 4.6 Write unit test for non-existent entity reference scenario
- [x] 4.7 Write unit test for nested object reference error scenario
- [x] 4.8 Write unit test for invalid enum value scenario
- [x] 4.9 Write unit test for multiple validation errors scenario
- [x] 4.10 Write unit test for valid write operation scenario

## 5. Documentation

- [x] 5.1 Add API docstrings to SchemaValidator class
- [x] 5.2 Document ValidationResult structure in SDK documentation
- [x] 5.3 Add usage example to core module README