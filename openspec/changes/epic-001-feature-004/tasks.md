## 1. Create Exception Module

- [x] 1.1 Create `hippo/core/exceptions.py` with HippoError base class
- [x] 1.2 Add ConfigError and SchemaError subclasses
- [x] 1.3 Add ValidationError and EntityNotFoundError subclasses
- [x] 1.4 Add AdapterError subclass with adapter context
- [x] 1.5 Add error message formatting utilities to each exception class

## 2. Update Existing Code

- [x] 2.1 Find all places in codebase that raise errors related to config
- [x] 2.2 Find all places in codebase that raise errors related to schema
- [x] 2.3 Find all places in codebase that raise errors related to entity lookup
- [x] 2.4 Find all places in codebase that raise errors related to adapters
- [x] 2.5 Update code to use appropriate new exception types

## 3. Add Tests

- [x] 3.1 Write test for ConfigError with invalid YAML syntax
- [x] 3.2 Write test for ConfigError with missing required fields
- [x] 3.3 Write test for SchemaError with invalid JSON Schema
- [x] 3.4 Write test for EntityNotFoundError
- [x] 3.5 Write test for AdapterError with invalid configuration
- [x] 3.6 Verify all acceptance criteria pass

## 4. Documentation

- [x] 4.1 Add docstrings to all exception classes
- [x] 4.2 Document error hierarchy in relevant documentation
