## 1. Test Infrastructure Setup

- [x] 1.1 Create test module directory structure
- [x] 1.2 Set up conftest.py with test fixtures (HippoClient, in-memory storage)
- [x] 1.3 Configure pytest to use in-memory SQLite for fast execution

## 2. Positive Case Tests

- [x] 2.1 Implement test for valid data with all required fields
- [x] 2.2 Implement test verifying entity is persisted after successful write

## 3. Required Field Validation Tests

- [x] 3.1 Implement test for missing required string field
- [x] 3.2 Implement test for missing required integer field
- [x] 3.3 Verify error messages include field name and expected type

## 4. Foreign Key Validation Tests

- [x] 4.1 Implement test for invalid foreign key reference
- [x] 4.2 Verify error indicates invalid reference with field identification

## 5. Data Type Validation Tests

- [x] 5.1 Implement test for string in numeric field
- [x] 5.2 Implement test for integer in string field
- [x] 5.3 Verify error identifies problematic field and expected type

## 6. Constraint Validation Tests

- [x] 6.1 Implement test for string exceeding max_length
- [x] 6.2 Implement test for array exceeding max_items
- [x] 6.3 Verify error specifies the exceeded limit

## 7. Test Refinement

- [x] 7.1 Run all tests and verify they pass
- [x] 7.2 Add parametrized tests for multiple entity types
- [x] 7.3 Review test coverage against spec scenarios
