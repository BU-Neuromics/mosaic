## 1. Enable OpenAPI Documentation in App Factory

- [x] 1.1 Modify `hippo/api/factory.py` to enable docs endpoint via `enable_docs()`
- [x] 1.2 Add OpenAPI schema endpoint configuration to app factory
- [x] 1.3 Configure basic API info (title, version) for OpenAPI schema

## 2. Verify Route Inclusion

- [x] 2.1 Verify all existing routers are included in OpenAPI spec
- [x] 2.2 Verify endpoint docstrings appear in the schema
- [x] 2.3 Verify response models are properly documented

## 3. Testing

- [x] 3.1 Test GET /docs returns HTTP 200 with text/html
- [x] 3.2 Test GET /openapi.json returns HTTP 200 with application/json
- [x] 3.3 Test Swagger UI renders and displays all endpoints
- [x] 3.4 Test endpoint filtering works in Swagger UI