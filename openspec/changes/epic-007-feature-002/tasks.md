## 1. CLI Setup

- [x] 1.1 Add Click dependency to project requirements (Skipped: uses Typer)
- [x] 1.2 Create CLI module structure (hippo/cli/__init__.py)
- [x] 1.3 Implement hippo init command entry point

## 2. Core Initialization Logic

- [x] 2.1 Create InitCommand class in CLI module
- [x] 2.2 Implement directory creation logic with path validation
- [x] 2.3 Create default config.json template generator
- [x] 2.4 Create default README.md template generator
- [x] 2.5 Create default .gitignore template generator

## 3. Template System

- [x] 3.1 Define template registry (basic, minimal, full)
- [x] 3.2 Implement template loader and validator
- [x] 3.3 Add --template CLI option parsing
- [x] 3.4 Implement template file generation without overwriting

## 4. Error Handling

- [x] 4.1 Detect existing config.json and raise error with guidance
- [x] 4.2 Validate template name and list available templates on invalid
- [x] 4.3 Handle permission denied errors with clear message

## 5. Testing

- [x] 5.1 Write unit tests for InitCommand
- [x] 5.2 Write integration tests for hippo init command
- [x] 5.3 Test error handling scenarios
- [x] 5.4 Test template selection and file generation
