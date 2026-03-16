## 1. Core Model Implementation

- [x] 1.1 Create HippoConfig Pydantic model class with required fields
- [x] 1.2 Add type annotations and validators for each field
- [x] 1.3 Implement ConfigError exception class
- [x] 1.4 Implement ValidationError exception class

## 2. Environment Variable Substitution

- [x] 2.1 Create env var substitution function with ${VAR} syntax
- [x] 2.2 Handle undefined environment variables with ConfigError
- [x] 2.3 Support nested environment variable substitution

## 3. YAML Loader Implementation

- [x] 3.1 Create hippo.yaml loader function
- [x] 3.2 Integrate env var substitution into loader
- [x] 3.3 Wire Pydantic validation into loader
- [x] 3.4 Return typed HippoConfig instance on success

## 4. Error Handling

- [x] 4.1 Ensure ConfigError includes missing field names
- [x] 4.2 Ensure ValidationError includes type mismatch details
- [x] 4.3 Add tests for error message content

## 5. Testing

- [x] 5.1 Write unit test for valid YAML with env vars
- [x] 5.2 Write unit test for undefined env var error
- [x] 5.3 Write unit test for missing required field error
- [x] 5.4 Write unit test for incorrect type error
- [x] 5.5 Write unit test for valid YAML without env vars