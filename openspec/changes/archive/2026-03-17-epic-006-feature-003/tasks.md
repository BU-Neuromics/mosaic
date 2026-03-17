## 1. Core SDK - AuthMiddleware Implementation

- [x] 1.1 Create hippo/core/middleware.py with AuthMiddleware ABC
- [x] 1.2 Implement PassThroughAuthMiddleware class
- [x] 1.3 Add request context dataclass for actor identification
- [x] 1.4 Add __init__.py exports for middleware module

## 2. FastAPI Transport Layer Integration

- [x] 2.1 Update hippo/serve/app.py to register PassThroughAuthMiddleware
- [x] 2.2 Configure middleware to process all routes

## 3. Testing

- [x] 3.1 Write unit tests for PassThroughAuthMiddleware (valid header scenario)
- [x] 3.2 Write unit tests for missing header scenario
- [x] 3.3 Write unit tests for invalid header format scenario
- [x] 3.4 Write unit tests for empty identifier scenario
- [x] 3.5 Write unit tests for multiple headers scenario

## 4. Verification

- [x] 4.1 Run existing test suite to ensure no regressions
- [x] 4.2 Verify middleware integrates correctly with FastAPI app
