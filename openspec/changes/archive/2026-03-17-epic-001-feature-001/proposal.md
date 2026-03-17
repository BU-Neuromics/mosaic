# HippoConfig Pydantic Model Implementation

## Goal
HippoConfig Pydantic Model Implementation: Implement the HippoConfig Pydantic model with validation and hippo.yaml loader supporting environment variable substitution for configuration parsing.

## Acceptance Criteria
- Given a valid hippo.yaml file with environment variables defined, when the loader processes it, then environment variables are properly substituted in the parsed model
- Given an invalid hippo.yaml file with missing required fields, when the loader processes it, then a ConfigError is raised with a clear error message indicating the missing field
- Given a hippo.yaml file with incorrect data types for fields, when the loader processes it, then a ValidationError is raised with descriptive information about the type mismatch
- Given a hippo.yaml file with environment variable references that are not defined in the system, when the loader processes it, then a ConfigError is raised with a clear error message indicating the undefined variable
- Given a valid hippo.yaml file without any environment variables, when the loader processes it, then the parsed model contains the exact values as specified in the file

## Constraints
- Complexity: medium
