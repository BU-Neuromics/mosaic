# Base Validator Infrastructure

## Goal
Base Validator Infrastructure: Implement the foundational abstract base class and data structures for write validation including WriteValidator ABC, WriteOperation dataclass, and ValidationResult dataclass.

## Acceptance Criteria
- Given a validator implements WriteValidator ABC, when the validate method is called with valid input that meets all validation rules, then it returns a successful ValidationResult with success set to true
- Given a validator implements WriteValidator ABC, when the validate method is called with invalid input that fails one or more validation rules, then it returns a failed ValidationResult with success set to false and appropriate error details in the errors field
- Given a validator implements WriteValidator ABC, when the validate method is called with null or empty input, then it returns a failed ValidationResult with a clear error message indicating invalid input
- Given a WriteOperation dataclass is instantiated, when the object is created with valid parameters for all required fields, then all fields are correctly assigned and accessible through getters
- Given a WriteOperation dataclass is instantiated, when the object is created with missing required fields, then it raises a TypeError exception during instantiation
- Given a ValidationResult dataclass is instantiated, when the object is created with valid success and errors parameters, then the fields are correctly assigned and accessible
- Given a ValidationResult dataclass is instantiated, when the object is created with invalid parameters (e.g., non-iterable errors), then it raises a TypeError exception during instantiation
- Given a WriteValidator ABC is defined, when a concrete validator class inherits from it, then the validate method must be implemented or an exception is raised during instantiation

## Constraints
- Complexity: low
