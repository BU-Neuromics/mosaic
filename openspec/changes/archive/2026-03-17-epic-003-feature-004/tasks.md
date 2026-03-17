## 1. Pipeline Core Implementation

- [x] 1.1 Create `hippo/core/pipeline.py` with ValidationPipeline class
- [x] 1.2 Implement `add_validator()` method for registering validators
- [x] 1.3 Implement `execute()` method with sequential fail-fast logic
- [x] 1.4 Implement `execute_all()` method (optional, for reporting all failures)
- [x] 1.5 Add validator order preservation and exactly-once guarantee

## 2. Validation Failure Handling

- [x] 2.1 Create `hippo/core/exceptions.py` with ValidationFailure exception
- [x] 2.2 Include rule_id, message, and input_context in ValidationFailure
- [x] 2.3 Add helper method to format detailed failure messages

## 3. HippoClient Integration

- [x] 3.1 Add `validate()` method to HippoClient
- [x] 3.2 Wire ValidationPipeline into write operations (create, update, delete)
- [x] 3.3 Ensure no bypass paths exist for write operations
- [x] 3.4 Add `bypass_validation` flag (deprecated) for backward compatibility

## 4. Configuration Integration

- [x] 4.1 Update SchemaConfig to load validator definitions from YAML/JSON
- [x] 4.2 Register built-in validators from features 001-003
- [x] 4.3 Add custom validator support in schema configuration
- [x] 4.4 Add validation pipeline configuration to settings

## 5. Testing

- [x] 5.1 Write unit tests for ValidationPipeline class
- [x] 5.2 Write unit tests for ValidationFailure exception
- [x] 5.3 Write integration tests for HippoClient validation
- [x] 5.4 Write tests for custom validator execution
- [x] 5.5 Write tests for validation order guarantee

## 6. Documentation

- [x] 6.1 Add API documentation for ValidationPipeline
- [x] 6.2 Add usage examples for custom validators
- [x] 6.3 Update README with validation pipeline setup
