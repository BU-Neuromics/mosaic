## 1. Core Implementation

- [x] 1.1 Create EntityNotFoundError exception class in hippo/api/exceptions.py
- [x] 1.2 Create ErrorResponse Pydantic model in hippo/api/schemas.py
- [x] 1.3 Implement create_app() factory function in hippo/api/factory.py
- [x] 1.4 Add global exception handlers for ValidationError, EntityNotFoundError, and generic Exception
- [x] 1.5 Export factory and exceptions from hippo/api/__init__.py

## 2. Testing

- [x] 2.1 Write test for factory creates app with routers
- [x] 2.2 Write test for factory creates app without routers
- [x] 2.3 Write test for ValidationError handler returns 422
- [x] 2.4 Write test for EntityNotFoundError handler returns 404
- [x] 2.5 Write test for generic Exception handler returns 500

## 3. Integration

- [x] 3.1 Verify factory works with hippo serve command
- [x] 3.2 Verify error responses have consistent format
