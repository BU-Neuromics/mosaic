## ADDED Requirements

### Requirement: Validators load from validators.yaml during write operations
Given a write operation with configured validators, when validation occurs, then all relevant validators SHALL be loaded from validators.yaml and executed in the correct order during the write process.

#### Scenario: Validators execute in defined order
- **WHEN** a write operation is performed with multiple validators configured in validators.yaml
- **THEN** validators are loaded and executed in the order defined in validators.yaml

#### Scenario: Validator execution during create
- **WHEN** a create operation triggers validation
- **THEN** all configured validators execute before the entity is persisted

#### Scenario: Validator execution during update
- **WHEN** an update operation triggers validation
- **THEN** all configured validators execute before the changes are committed

### Requirement: Validators execute independently without side effects
Given multiple validators are configured in validators.yaml with different validation rules, when validation runs, then each validator SHALL execute independently without side effects and return correct validation results.

#### Scenario: Independent validator execution
- **WHEN** multiple validators are configured for a write operation
- **THEN** each validator operates on a copy of the context data and does not affect other validators

#### Scenario: Validator isolation
- **WHEN** a validator throws an exception during execution
- **THEN** other validators are not affected and can still execute

### Requirement: Validation failures roll back changes and return detailed errors
Given validation fails for any rule in the write path, when the write operation is committed, then it SHALL properly roll back changes and return a detailed error message specific to the failed validation rule.

#### Scenario: Rollback on validation failure
- **WHEN** a validator returns a validation error during write operation
- **THEN** all changes are rolled back and an error is returned with the specific validation failure details

#### Scenario: Detailed error message format
- **WHEN** validation fails
- **THEN** the error message includes the validator name, rule name, and failure reason

### Requirement: Feature dependencies initialize before validator execution
Given a validator with dependency on feature-001, when validation occurs, then the dependent feature SHALL be properly initialized before validator execution.

#### Scenario: Feature dependency initialization
- **WHEN** a validator specifies a dependency on feature-001
- **THEN** feature-001 is initialized and available before the validator executes

#### Scenario: Feature availability check
- **WHEN** a validator depends on feature-001 and feature-001 fails to initialize
- **THEN** validation fails with an appropriate error indicating the dependency issue

### Requirement: Missing feature dependencies return appropriate errors
Given a validator with dependency on feature-002, when validation occurs, then the validator SHALL correctly handle cases where the dependency is not available and return appropriate error details.

#### Scenario: Missing dependency handling
- **WHEN** a validator depends on feature-002 but feature-002 is not available
- **THEN** validation fails with a clear error message indicating the missing dependency

#### Scenario: Dependency error details
- **WHEN** a required feature dependency is unavailable
- **THEN** the error includes the feature name and reason for unavailability

### Requirement: Nested validation rules expand and execute correctly
Given validators.yaml contains nested validation rules, when validation runs, then all nested rules SHALL be expanded and executed correctly within the write process.

#### Scenario: Nested rule expansion
- **WHEN** a validator contains nested rules in its configuration
- **THEN** all nested rules are expanded and executed as individual validation steps

#### Scenario: Nested rule ordering
- **WHEN** nested rules exist in validator configuration
- **THEN** nested rules execute in the order they are defined, maintaining parent-child relationship

### Requirement: External API timeouts are handled as validation errors
Given a validator that performs external API calls, when validation runs, then it SHALL properly handle timeout conditions and return timeouts as validation errors.

#### Scenario: API timeout handling
- **WHEN** a validator makes an external API call that exceeds the timeout threshold
- **THEN** the validation fails with a timeout error including the API endpoint and timeout duration

#### Scenario: Timeout error format
- **WHEN** a validator experiences a timeout
- **THEN** the error message includes "timeout", the endpoint URL, and the timeout value

### Requirement: Invalid validator configuration loads valid validators with warnings
Given an invalid configuration in validators.yaml, when the system attempts to load validators, then it SHALL load only valid validators and log appropriate warnings for invalid entries.

#### Scenario: Partial validator loading
- **WHEN** validators.yaml contains one valid and one invalid validator configuration
- **THEN** only the valid validator is loaded and a warning is logged for the invalid entry

#### Scenario: Invalid config warning
- **WHEN** an invalid validator configuration is encountered
- **THEN** a warning is logged with details about the invalid configuration including the path and error

### Requirement: Write operations with no validators proceed without validation overhead
Given a write operation with no validators configured, when validation occurs, then the operation SHALL proceed without any validation overhead.

#### Scenario: No validators configured
- **WHEN** a write operation is performed with no validators configured in validators.yaml
- **THEN** the write operation proceeds directly without any validation steps

### Requirement: Validators can modify context for subsequent validators
Given a validator that modifies context data during execution, when validation runs, then subsequent validators SHALL receive updated context data as expected.

#### Scenario: Context data propagation
- **WHEN** validator A modifies a value in the context during execution
- **THEN** validator B receives the modified context with the updated value

#### Scenario: Chained context updates
- **WHEN** multiple validators modify context data sequentially
- **THEN** each validator sees the cumulative changes from all previous validators