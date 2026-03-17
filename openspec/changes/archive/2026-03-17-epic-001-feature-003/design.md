## Context

This change implements shared SDK types for the Hippo Core SDK. These types provide consistent data handling across the SDK's public API. The types needed are: Filter, PaginatedResult, ScoredMatch, WriteOperation, ValidationResult, ProvenanceRecord, and IngestResult.

## Goals / Non-Goals

**Goals:**
- Implement all seven core SDK types with proper TypeScript typing
- Ensure types are semantically correct and match acceptance criteria
- Provide type safety for SDK operations

**Non-Goals:**
- Implementing actual business logic that uses these types
- Database schema changes
- API endpoint implementations

## Decisions

1. **Type Definitions Approach**: Using TypeScript interfaces for all types for compile-time type safety and IDE support.

2. **Pagination Structure**: PaginatedResult will include `items`, `total`, `page`, and `pageSize` fields.

3. **Validation Structure**: ValidationResult will use a `valid: boolean` flag with optional `errors` array containing `{ field: string, message: string }` objects.

4. **Provenance Tracking**: ProvenanceRecord will include `source`, `timestamp`, and `operation` fields.

## Risks / Trade-offs

- Low risk: These are pure type definitions with no runtime complexity
- No significant trade-offs identified for this straightforward types implementation