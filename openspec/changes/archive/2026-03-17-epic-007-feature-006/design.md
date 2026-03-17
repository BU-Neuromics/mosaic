## Context

This change implements schema compilation and validation features for the Hippo metadata tracking system. The feature allows developers to compile schemas from JSON format into a system-readable format, validate schemas against defined rules, and compare different versions of schemas.

The implementation depends on feature-001 which provides core functionality for schema processing within the hippo CLI.

## Goals / Non-Goals

**Goals:**
- Implement 'hippo compile-schema' command that transforms JSON schema files into system-readable format
- Implement 'hippo validate --schema <file>' command that validates schema against defined rules
- Implement 'hippo schema diff' command that compares two schema versions and shows differences
- Provide clear error messages for syntax and validation errors
- Support both valid and invalid schema file scenarios

**Non-Goals:**
- Core data model changes beyond schema handling
- UI components or web interface for schema management
- Database integration or persistence of compiled schemas
- Performance optimization for very large schemas (initial implementation focus)

## Decisions

- Schema compilation will use existing JSON parsing with LinkML transformation for consistency 
- Validation will apply rules defined in the schema's validation section
- Error messages will include file location, error type, and clear descriptive text
- Schema diff will provide human-readable output showing added/removed/modified elements
- All commands will follow CLI conventions established by other hippo commands

## Risks / Trade-offs

- **Complexity of JSON parsing**: Large or malformed JSON files could cause performance issues → Implement streaming parsers with error recovery
- **Validation rules complexity**: Adding too many validation rules may slow down processing → Focus on core validation, allow extensible rule systems
- **Schema diff accuracy**: Differences between versions might be hard to interpret → Include clear format showing additions/removals and modified elements
- **Error handling consistency**: Inconsistent error messages across commands → Implement standardized error response structure

## Migration Plan

- New functionality will be added to existing CLI structure
- No breaking changes to existing commands or behavior
- Commands will fail gracefully on invalid inputs, with appropriate error codes
- Existing users won't be affected by the addition of these new features

## Open Questions

- Should schema compilation cache results for faster repeated calls? 
- What level of detail should be shown in schema diff output?
- How should error messages be formatted for localization support?