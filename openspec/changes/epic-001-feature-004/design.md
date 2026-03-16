## Context

This change implements a complete error hierarchy for the Hippo SDK. Currently, error handling is likely ad-hoc or uses generic exceptions. A structured error hierarchy improves debugging, allows callers to catch specific error types, and provides consistent error messages across the system.

The proposal defines 6 base error types with subclasses: HippoError (base), ConfigError, SchemaError, ValidationError, EntityNotFoundError, and AdapterError.

## Goals / Non-Goals

**Goals:**
- Create a base `HippoError` exception class that all Hippo exceptions inherit from
- Implement specific error types: `ConfigError`, `SchemaError`, `ValidationError`, `EntityNotFoundError`, `AdapterError`
- Each error type should support context-rich messages (e.g., showing what field is missing or where parsing failed)
- Ensure all existing code that raises errors uses the new hierarchy
- Maintain backward compatibility for any existing error catching

**Non-Goals:**
- Error logging or reporting infrastructure (separate concern)
- Internationalization/localization of error messages
- Automatic error recovery mechanisms

## Decisions

1. **Base class inheritance structure:**
   - `HippoError(Exception)` - base for all Hippo exceptions
   - `ConfigError(HippoError)` - config loading/validation errors
   - `SchemaError(HippoError)` - schema parsing/processing errors
   - `ValidationError(HippoError)` - data validation errors
   - `EntityNotFoundError(HippoError)` - when an entity doesn't exist
   - `AdapterError(HippoError)` - adapter-specific errors

2. **Error message format:** Each error accepts keyword arguments (e.g., `field`, `location`, `details`) that get incorporated into the error message for better debugging.

3. **Location in codebase:** Create `hippo/core/exceptions.py` to hold all exception classes.

## Risks / Trade-offs

- **Risk:** Existing code catching `Exception` will still work, but lose specificity. → Mitigation: Document the new hierarchy and encourage catching specific types.
- **Risk:** Adding new error types requires updating multiple places. → Mitigation: Keep the hierarchy simple and well-documented.
- **Trade-off:** More classes vs. cleaner error handling. → Decision: The benefits of specific error types outweigh the minimal added complexity.

## Migration Plan

1. Create `hippo/core/exceptions.py` with all error classes
2. Update existing code to use new error types instead of generic exceptions
3. Add tests verifying each error type is raised in the correct scenario
4. No database migration needed (pure code change)

## Open Questions

None at this time. The proposal provides clear acceptance criteria.
