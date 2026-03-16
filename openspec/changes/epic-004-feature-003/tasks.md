## 1. Database Schema

- [x] 1.1 Create `entity_external_ids` table with columns: `id`, `entity_id`, `external_id`, `created_at`, `superseded_at`
- [x] 1.2 Add index on `(external_id, created_at DESC)` for efficient latest-lookup queries
- [x] 1.3 Add foreign key constraint from `entity_external_ids.entity_id` to main entity table

## 2. Storage Adapter

- [x] 2.1 Create `ExternalIdStorageAdapter` class with CRUD operations
- [x] 2.2 Implement `create_external_id(entity_id, external_id)` method
- [x] 2.3 Implement `get_entity_by_external_id(external_id)` with latest-timestamp logic
- [x] 2.4 Implement `list_external_ids_for_entity(entity_id)` method
- [x] 2.5 Implement `supersede_external_id(entity_id, old_external_id, new_external_id)` method

## 3. SDK Implementation

- [x] 3.1 Add `register_external_id(entity_id, external_id)` method to HippoClient
- [x] 3.2 Add `supersede(entity_id, old_external_id, new_external_id)` method to HippoClient
- [x] 3.3 Add `get_by_external_id(external_id)` method to HippoClient
- [x] 3.4 Integrate ExternalIdStorageAdapter with QueryEngine

## 4. Testing

- [x] 4.1 Write unit tests for ExternalIdStorageAdapter methods
- [x] 4.2 Write integration tests for HippoClient external ID methods
- [x] 4.3 Test edge cases: concurrent registrations, multiple entities with same external ID
- [x] 4.4 Run existing test suite to ensure no regressions
