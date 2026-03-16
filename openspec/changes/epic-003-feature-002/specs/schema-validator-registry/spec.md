## ADDED Requirements

### Requirement: Validator discovery via entry points
The registry SHALL discover validators registered via the `hippo.validators` entry point group.

#### Scenario: Validator registered via entry point is discovered
- **WHEN** a validator is registered via entry point in a package's setup.py or pyproject.toml
- **THEN** the registry includes the validator in its list of available validators

### Requirement: Validators ordered by priority descending
The registry SHALL sort validators by priority value in descending order (higher priority first).

#### Scenario: Validators with different priorities are ordered correctly
- **WHEN** multiple validators with different priorities are registered
- **THEN** the registry returns validators sorted by priority in descending order

#### Scenario: Priority 10 appears before priority 5
- **WHEN** a validator with priority 10 is registered alongside a validator with priority 5
- **THEN** the validator with priority 10 appears before the validator with priority 5 in the ordered list

### Requirement: Pipeline executes all validators in priority order
The pipeline SHALL execute all registered validators in correct priority order from highest to lowest.

#### Scenario: Write operation executes all validators in order
- **WHEN** a write operation is performed
- **THEN** all validators execute in correct priority order from highest to lowest

#### Scenario: Each validator executes exactly once
- **WHEN** a write operation is performed with multiple registered validators
- **THEN** each validator's execute method is called exactly once in the correct priority order
