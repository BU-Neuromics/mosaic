## 1. Project Setup

- [x] 1.1 Add FastAPI and Pydantic dependencies to project
- [x] 1.2 Create hippo/serve/ directory structure
- [x] 1.3 Configure OpenAPI documentation settings

## 2. Core Router Infrastructure

- [x] 2.1 Create base router class with authentication
- [x] 2.2 Implement error handling middleware (RFC 7807)
- [x] 2.3 Add request validation utilities
- [x] 2.4 Create health check endpoint

## 3. Entity Router

- [x] 3.1 Implement GET /entities endpoint
- [x] 3.2 Implement GET /entities/{id} endpoint
- [x] 3.3 Add query parameter filtering support
- [x] 3.4 Implement entity type filtering
- [x] 3.5 Add pagination support

## 4. Ingest Router

- [x] 4.1 Implement POST /ingest endpoint
- [x] 4.2 Add required field validation
- [x] 4.3 Implement JSON parsing error handling
- [x] 4.4 Return 201 with created entity

## 5. Search Router

- [x] 5.1 Implement GET /search endpoint
- [x] 5.2 Add query parameter search support
- [x] 5.3 Implement pagination (limit/offset)

## 6. History Router

- [x] 6.1 Implement GET /entities/{id}/history endpoint
- [x] 6.2 Connect to ProvenanceManager

## 7. Availability Router

- [x] 7.1 Implement GET /entities/{id}/availability endpoint
- [x] 7.2 Implement POST /entities/{id}/availability endpoint

## 8. Supersede Router

- [x] 8.1 Implement POST /entities/{id}/supersede endpoint
- [x] 8.2 Implement GET /entities/{id}/superseded endpoint

## 9. Relationship Router

- [x] 9.1 Implement GET /entities/{id}/relationships endpoint
- [x] 9.2 Implement POST /entities/{id}/relationships endpoint
- [x] 9.3 Implement DELETE /entities/{id}/relationships/{rel_id} endpoint

## 10. External ID Router

- [x] 10.1 Implement GET /external-ids/{id_type}/{external_id} endpoint
- [x] 10.2 Implement GET /entities/{id}/external-ids endpoint
- [x] 10.3 Implement POST /entities/{id}/external-ids endpoint

## 11. Schema Router

- [x] 11.1 Implement GET /schemas endpoint
- [x] 11.2 Implement GET /schemas/{schema_name} endpoint
- [x] 11.3 Implement POST /schemas endpoint

## 12. Testing & Documentation

- [x] 12.1 Add unit tests for each router
- [x] 12.2 Add integration tests for API endpoints
- [x] 12.3 Verify OpenAPI documentation generates correctly
- [x] 12.4 Test authentication flow
