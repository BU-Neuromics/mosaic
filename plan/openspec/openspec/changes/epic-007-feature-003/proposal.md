# Schema Migration Engine Implementation

## Goal
Schema Migration Engine Implementation: Develop the schema diff engine that detects additive changes and manages database migrations.

## Acceptance Criteria
- Given a user has an existing database schema, when they run 'hippo migrate', then the system detects schema changes and generates appropriate migration plans
- Given a user modifies a schema definition by adding new tables, columns, or indexes, when they run 'hippo migrate', then additive changes are properly identified as new migration steps
- Given a user runs 'hippo migrate --preview', when they request preview mode, then the system outputs the planned migration actions without applying them
- Given a user has a database with existing data, when they add a non-nullable column to a table, then the system generates a migration that handles existing rows appropriately
- Given a user modifies a schema definition by adding constraints or indexes, when they run 'hippo migrate', then the system properly identifies and includes these additive changes in migration steps
- Given a user runs 'hippo migrate' on an empty database, when no schema changes are detected, then the system reports that no migrations are needed
- Given a user modifies multiple schema elements in a single definition file, when they run 'hippo migrate', then the system correctly identifies all changes and generates appropriate migration steps for each change
- Given a user runs 'hippo migrate' with conflicting schema definitions, when the system detects inconsistencies, then it properly reports errors and does not generate invalid migrations

## Constraints
- Depends on: feature-001
- Complexity: high
