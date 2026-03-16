import pytest

from hippo.core.exceptions import (
    AdapterError,
    ConfigError,
    EntityNotFoundError,
    HippoError,
    SchemaError,
    ValidationError,
    ValidationFailure,
)


class TestHippoError:
    def test_base_exception_message(self):
        err = HippoError("Something went wrong")
        assert err.message == "Something went wrong"
        assert "Something went wrong" in str(err)

    def test_base_exception_with_context(self):
        err = HippoError("Operation failed", operation="read", resource="file.txt")
        assert err.context["operation"] == "read"
        assert err.context["resource"] == "file.txt"
        assert "operation='read'" in str(err)


class TestConfigError:
    def test_config_error_with_field_name(self):
        err = ConfigError("Missing required field", field_name="schema_path")
        assert err.field_name == "schema_path"
        assert "schema_path" in str(err)
        assert "Missing required field" in err.message

    def test_config_error_without_field_name(self):
        err = ConfigError("Configuration file not found")
        assert err.field_name is None
        assert "Configuration file not found" in str(err)

    def test_invalid_yaml_syntax(self):
        err = ConfigError("invalid YAML syntax: mapping error")
        assert "invalid yaml syntax" in err.message.lower()

    def test_missing_required_field(self):
        err = ConfigError("Missing required field", field_name="schema_path")
        assert err.field_name == "schema_path"
        assert "schema_path" in str(err)


class TestSchemaError:
    def test_schema_error_with_code(self):
        err = SchemaError("Schema validation failed", error_code="VALIDATION_ERROR")
        assert err.error_code == "VALIDATION_ERROR"
        assert "VALIDATION_ERROR" in str(err)

    def test_schema_error_with_field(self):
        err = SchemaError(
            "Invalid field", error_code="INVALID_FIELD", field_name="my_field"
        )
        assert err.field_name == "my_field"
        assert "my_field" in str(err)

    def test_schema_error_with_cycle_path(self):
        err = SchemaError(
            "Circular inheritance detected",
            error_code="CYCLE_DETECTED",
            cycle_path=["schema_a", "schema_b", "schema_a"],
        )
        assert len(err.cycle_path) == 3
        assert "schema_a" in str(err)


class TestValidationError:
    def test_validation_error_with_types(self):
        err = ValidationError(
            "Type mismatch",
            expected_type="string",
            actual_value=123,
            field_name="my_field",
        )
        assert err.expected_type == "string"
        assert err.actual_value == 123
        assert err.field_name == "my_field"
        assert "string" in str(err)
        assert "123" in str(err)

    def test_validation_error_without_types(self):
        err = ValidationError("Validation failed")
        assert err.expected_type is None
        assert err.actual_value is None


class TestEntityNotFoundError:
    def test_entity_not_found_with_id(self):
        err = EntityNotFoundError(
            "Entity not found", entity_type="Sample", entity_id="sample-123"
        )
        assert err.entity_type == "Sample"
        assert err.entity_id == "sample-123"
        assert "Sample" in str(err)
        assert "sample-123" in str(err)

    def test_entity_not_found_without_id(self):
        err = EntityNotFoundError("Entity not found", entity_type="Sample")
        assert err.entity_type == "Sample"
        assert err.entity_id is None


class TestAdapterError:
    def test_adapter_error_with_config(self):
        err = AdapterError(
            "Adapter configuration invalid",
            adapter_name="sqlite",
            adapter_type="storage",
        )
        assert err.adapter_name == "sqlite"
        assert err.adapter_type == "storage"
        assert "sqlite" in str(err)
        assert "storage" in str(err)

    def test_adapter_error_without_config(self):
        err = AdapterError("Adapter failed")
        assert err.adapter_name is None
        assert err.adapter_type is None


class TestErrorHierarchy:
    def test_all_errors_inherit_from_hippo_error(self):
        errors = [
            ConfigError("test"),
            SchemaError("test", error_code="TEST"),
            ValidationError("test"),
            EntityNotFoundError("test"),
            AdapterError("test"),
        ]
        for err in errors:
            assert isinstance(err, HippoError)

    def test_config_error_catchable_as_hippo_error(self):
        try:
            raise ConfigError("test error", field_name="test_field")
        except HippoError as e:
            assert "test error" in str(e)

    def test_schema_error_catchable_as_hippo_error(self):
        try:
            raise SchemaError("test error", error_code="TEST")
        except HippoError as e:
            assert "test error" in str(e)

    def test_validation_error_catchable_as_hippo_error(self):
        try:
            raise ValidationError("test error")
        except HippoError as e:
            assert "test error" in str(e)

    def test_entity_not_found_error_catchable_as_hippo_error(self):
        try:
            raise EntityNotFoundError(
                "test error", entity_type="Sample", entity_id="123"
            )
        except HippoError as e:
            assert "test error" in str(e)

    def test_adapter_error_catchable_as_hippo_error(self):
        try:
            raise AdapterError("test error", adapter_name="test")
        except HippoError as e:
            assert "test error" in str(e)


class TestValidationFailure:
    def test_validation_failure_basic(self):
        err = ValidationFailure("Validation failed")
        assert err.message == "Validation failed"
        assert err.rule_id is None
        assert err.input_context == {}
        assert "Validation failed" in str(err)

    def test_validation_failure_with_rule_id(self):
        err = ValidationFailure(
            "Field is required",
            rule_id="required-field",
        )
        assert err.rule_id == "required-field"
        assert "required-field" in str(err)

    def test_validation_failure_with_input_context(self):
        err = ValidationFailure(
            "Invalid value",
            input_context={"name": "test", "value": 42},
        )
        assert err.input_context == {"name": "test", "value": 42}
        assert "test" in str(err)
        assert "42" in str(err)

    def test_validation_failure_with_entity_info(self):
        err = ValidationFailure(
            "Validation failed",
            entity_type="Sample",
            entity_id="sample-123",
        )
        assert err.entity_type == "Sample"
        assert err.entity_id == "sample-123"
        assert "Sample" in str(err)
        assert "sample-123" in str(err)

    def test_format_detailed_message(self):
        err = ValidationFailure(
            "Field is required",
            rule_id="required-field",
            input_context={"id": "123"},
            entity_type="Sample",
            entity_id="123",
        )
        detailed = err.format_detailed_message()
        assert "Field is required" in detailed
        assert "Rule: required-field" in detailed
        assert "Entity type: Sample" in detailed

    def test_format_detailed_message_minimal(self):
        err = ValidationFailure("Simple error")
        detailed = err.format_detailed_message()
        assert detailed == "Simple error"

    def test_validation_failure_inherits_from_hippo_error(self):
        err = ValidationFailure("test")
        assert isinstance(err, HippoError)
