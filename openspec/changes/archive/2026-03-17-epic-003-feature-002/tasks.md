## 1. Validator Registry Implementation

- [x] 1.1 Create ValidatorRegistry class in hippo/core/validation/
- [x] 1.2 Implement entry point discovery using importlib.metadata
- [x] 1.3 Add priority-based ordering (descending sort)
- [x] 1.4 Add get_validators() method returning ordered list

## 2. Validator Pipeline Implementation

- [x] 2.1 Create ValidatorPipeline class
- [x] 2.2 Implement execute() method that runs all validators in order
- [x] 2.3 Ensure each validator's execute() is called exactly once
- [x] 2.4 Integrate pipeline with write operations

## 3. Entry Point Registration

- [x] 3.1 Add hippo.validators entry point group to package metadata
- [x] 3.2 Document entry point registration for external packages

## 4. Testing

- [x] 4.1 Write unit tests for ValidatorRegistry discovery
- [x] 4.2 Write unit tests for priority ordering
- [x] 4.3 Write integration tests for pipeline execution
