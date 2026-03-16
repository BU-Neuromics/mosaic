## 1. Core Infrastructure

- [x] 1.1 Create preset base classes in hippo/core/validation/presets/
- [x] 1.2 Define error types (ReferenceConstraintViolation, CountConstraintViolation, ImmutableFieldViolation, FieldRequiredViolation, SelfReferenceViolation)
- [x] 1.3 Add preset registry for built-in presets

## 2. ref_check Preset Implementation

- [x] 2.1 Implement RefCheckPreset class with reference validation logic
- [x] 2.2 Add reference constraint configuration schema
- [x] 2.3 Implement error message builder for reference violations

## 3. count_constraint Preset Implementation

- [x] 3.1 Implement CountConstraintPreset class with count validation logic
- [x] 3.2 Add count limit configuration schema
- [x] 3.3 Implement error message builder for count violations

## 4. immutable_field Preset Implementation

- [x] 4.1 Implement ImmutableFieldPreset class with field immutability logic
- [x] 4.2 Add immutable field configuration schema
- [x] 4.3 Implement error message builder for immutable field violations

## 5. field_required_if Preset Implementation

- [x] 5.1 Implement FieldRequiredIfPreset class with conditional requirement logic
- [x] 5.2 Add conditional requirement configuration schema
- [x] 5.3 Implement error message builder for required field violations

## 6. no_self_ref Preset Implementation

- [x] 6.1 Implement NoSelfRefPreset class with self-reference prevention logic
- [x] 6.2 Add self-reference configuration schema
- [x] 6.3 Implement error message builder for self-reference violations

## 7. Integration & Testing

- [x] 7.1 Register all five presets in the preset registry
- [x] 7.2 Add integration tests for each preset
- [x] 7.3 Update schema compilation to include built-in presets
