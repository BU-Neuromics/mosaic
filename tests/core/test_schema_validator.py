"""Tests for SchemaValidator."""

import pytest

from hippo.core.validation import (
    SchemaValidationConfig,
    SchemaValidator,
    ValidationResult,
    WriteOperation,
)
from hippo.config.models import SchemaConfig, FieldDefinition


def create_sample_schema() -> SchemaConfig:
    """Create a sample schema for testing."""
    return SchemaConfig(
        name="Sample",
        version="1.0",
        fields=[
            FieldDefinition(name="id", type="string", required=True),
            FieldDefinition(name="name", type="string", required=True),
            FieldDefinition(name="age", type="integer", required=False),
            FieldDefinition(name="score", type="float", required=False),
            FieldDefinition(name="active", type="boolean", required=False),
            FieldDefinition(name="created_at", type="datetime", required=False),
            FieldDefinition(
                name="status",
                type="enum",
                required=False,
                references={"values": ["active", "archived", "deleted"]},
            ),
            FieldDefinition(
                name="owner",
                type="string",
                required=False,
                references={"entity_type": "User"},
            ),
        ],
    )


class TestRequiredFieldValidation:
    """Tests for required field validation."""

    def test_missing_required_field_returns_error(self):
        """Task 4.1: Write unit test for missing required field scenario."""
        schema = create_sample_schema()
        config = SchemaValidationConfig(schemas={"Sample": schema})
        validator = SchemaValidator(config)

        op = WriteOperation(
            operation="insert", entity_type="Sample", data={"id": "123"}
        )
        result = validator.validate(op)

        assert result.is_valid is False
        assert "Field 'name' is required" in result.errors
        assert result.entity_id == "123"

    def test_present_required_field_passes(self):
        """Required field present passes validation."""
        schema = create_sample_schema()
        config = SchemaValidationConfig(schemas={"Sample": schema})
        validator = SchemaValidator(config)

        op = WriteOperation(
            operation="insert",
            entity_type="Sample",
            data={"id": "123", "name": "Test"},
        )
        result = validator.validate(op)

        assert result.is_valid is True
        assert len(result.errors) == 0


class TestStringTypeValidation:
    """Tests for string type validation."""

    def test_invalid_string_type_returns_error(self):
        """Task 4.2: Write unit test for invalid string type scenario."""
        schema = create_sample_schema()
        config = SchemaValidationConfig(schemas={"Sample": schema})
        validator = SchemaValidator(config)

        op = WriteOperation(
            operation="insert",
            entity_type="Sample",
            data={"id": "123", "name": 123},
        )
        result = validator.validate(op)

        assert result.is_valid is False
        assert "Expected string type for field 'name'" in result.errors

    def test_valid_string_passes(self):
        """Valid string passes validation."""
        schema = create_sample_schema()
        config = SchemaValidationConfig(schemas={"Sample": schema})
        validator = SchemaValidator(config)

        op = WriteOperation(
            operation="insert",
            entity_type="Sample",
            data={"id": "123", "name": "test"},
        )
        result = validator.validate(op)

        assert result.is_valid is True


class TestNumberTypeValidation:
    """Tests for number type validation."""

    def test_invalid_integer_type_returns_error(self):
        """Task 4.3: Write unit test for invalid number type scenario."""
        schema = create_sample_schema()
        config = SchemaValidationConfig(schemas={"Sample": schema})
        validator = SchemaValidator(config)

        op = WriteOperation(
            operation="insert",
            entity_type="Sample",
            data={"id": "123", "name": "test", "age": "not a number"},
        )
        result = validator.validate(op)

        assert result.is_valid is False
        assert "Expected integer type for field 'age'" in result.errors

    def test_invalid_float_type_returns_error(self):
        """Float field with wrong type returns error."""
        schema = create_sample_schema()
        config = SchemaValidationConfig(schemas={"Sample": schema})
        validator = SchemaValidator(config)

        op = WriteOperation(
            operation="insert",
            entity_type="Sample",
            data={"id": "123", "name": "test", "score": "not a float"},
        )
        result = validator.validate(op)

        assert result.is_valid is False
        assert "Expected number type for field 'score'" in result.errors


class TestBooleanTypeValidation:
    """Tests for boolean type validation."""

    def test_invalid_boolean_type_returns_error(self):
        """Task 4.4: Write unit test for invalid boolean type scenario."""
        schema = create_sample_schema()
        config = SchemaValidationConfig(schemas={"Sample": schema})
        validator = SchemaValidator(config)

        op = WriteOperation(
            operation="insert",
            entity_type="Sample",
            data={"id": "123", "name": "test", "active": "yes"},
        )
        result = validator.validate(op)

        assert result.is_valid is False
        assert "Expected boolean type for field 'active'" in result.errors


class TestTimestampValidation:
    """Tests for timestamp/datetime type validation."""

    def test_invalid_timestamp_format_returns_error(self):
        """Task 4.5: Write unit test for invalid timestamp format scenario."""
        schema = create_sample_schema()
        config = SchemaValidationConfig(schemas={"Sample": schema})
        validator = SchemaValidator(config)

        op = WriteOperation(
            operation="insert",
            entity_type="Sample",
            data={"id": "123", "name": "test", "created_at": "not a date"},
        )
        result = validator.validate(op)

        assert result.is_valid is False
        assert (
            "Expected ISO 8601 timestamp format for field 'created_at'" in result.errors
        )

    def test_valid_timestamp_passes(self):
        """Valid ISO 8601 timestamp passes validation."""
        schema = create_sample_schema()
        config = SchemaValidationConfig(schemas={"Sample": schema})
        validator = SchemaValidator(config)

        op = WriteOperation(
            operation="insert",
            entity_type="Sample",
            data={"id": "123", "name": "test", "created_at": "2024-01-15T10:30:00Z"},
        )
        result = validator.validate(op)

        assert result.is_valid is True


class TestEntityReferenceValidation:
    """Tests for entity reference validation."""

    def test_non_existent_entity_reference_returns_error(self):
        """Task 4.6: Write unit test for non-existent entity reference scenario."""
        schema = create_sample_schema()

        def entity_exists(entity_type, entity_id):
            return entity_id in ["user-1", "user-2"]

        config = SchemaValidationConfig(
            schemas={"Sample": schema}, entity_exists_fn=entity_exists
        )
        validator = SchemaValidator(config)

        op = WriteOperation(
            operation="insert",
            entity_type="Sample",
            data={"id": "123", "name": "test", "owner": "user-999"},
        )
        result = validator.validate(op)

        assert result.is_valid is False
        assert (
            "Reference to non-existent entity 'User' with ID 'user-999'"
            in result.errors
        )

    def test_existing_entity_reference_passes(self):
        """Existing entity reference passes validation."""
        schema = create_sample_schema()

        def entity_exists(entity_type, entity_id):
            return entity_id in ["user-1", "user-2"]

        config = SchemaValidationConfig(
            schemas={"Sample": schema}, entity_exists_fn=entity_exists
        )
        validator = SchemaValidator(config)

        op = WriteOperation(
            operation="insert",
            entity_type="Sample",
            data={"id": "123", "name": "test", "owner": "user-1"},
        )
        result = validator.validate(op)

        assert result.is_valid is True


class TestNestedReferenceValidation:
    """Tests for nested object reference validation."""

    def test_nested_object_reference_error(self):
        """Task 4.7: Write unit test for nested object reference error scenario."""
        schema = create_sample_schema()

        def entity_exists(entity_type, entity_id):
            return entity_id in ["user-1", "user-2"]

        config = SchemaValidationConfig(
            schemas={"Sample": schema}, entity_exists_fn=entity_exists
        )
        validator = SchemaValidator(config)

        op = WriteOperation(
            operation="insert",
            entity_type="Sample",
            data={"id": "123", "name": "test", "owner": {"id": "user-999"}},
        )
        result = validator.validate(op)

        assert result.is_valid is False
        assert (
            "Reference to non-existent entity 'User' in field 'owner'" in result.errors
        )


class TestEnumValidation:
    """Tests for enum validation."""

    def test_invalid_enum_value_returns_error(self):
        """Task 4.8: Write unit test for invalid enum value scenario."""
        schema = create_sample_schema()
        config = SchemaValidationConfig(schemas={"Sample": schema})
        validator = SchemaValidator(config)

        op = WriteOperation(
            operation="insert",
            entity_type="Sample",
            data={"id": "123", "name": "test", "status": "invalid"},
        )
        result = validator.validate(op)

        assert result.is_valid is False
        assert "Invalid enum value 'invalid'" in result.errors[0]
        assert "Expected one of [active, archived, deleted]" in result.errors[0]

    def test_valid_enum_value_passes(self):
        """Valid enum value passes validation."""
        schema = create_sample_schema()
        config = SchemaValidationConfig(schemas={"Sample": schema})
        validator = SchemaValidator(config)

        op = WriteOperation(
            operation="insert",
            entity_type="Sample",
            data={"id": "123", "name": "test", "status": "active"},
        )
        result = validator.validate(op)

        assert result.is_valid is True


class TestMultipleErrors:
    """Tests for multiple validation errors."""

    def test_multiple_validation_errors(self):
        """Task 4.9: Write unit test for multiple validation errors scenario."""
        schema = create_sample_schema()

        def entity_exists(entity_type, entity_id):
            return entity_id in ["user-1", "user-2"]

        config = SchemaValidationConfig(
            schemas={"Sample": schema}, entity_exists_fn=entity_exists
        )
        validator = SchemaValidator(config)

        op = WriteOperation(
            operation="insert",
            entity_type="Sample",
            data={
                "id": 123,
                "name": 456,
                "status": "bad",
                "owner": "user-999",
            },
        )
        result = validator.validate(op)

        assert result.is_valid is False
        assert len(result.errors) >= 3
        assert "Expected string type for field 'id'" in result.errors
        assert "Expected string type for field 'name'" in result.errors
        assert any("Invalid enum value 'bad'" in err for err in result.errors)


class TestValidWriteOperation:
    """Tests for valid write operations."""

    def test_valid_write_operation_passes(self):
        """Task 4.10: Write unit test for valid write operation scenario."""
        schema = create_sample_schema()

        def entity_exists(entity_type, entity_id):
            return entity_id in ["user-1", "user-2"]

        config = SchemaValidationConfig(
            schemas={"Sample": schema}, entity_exists_fn=entity_exists
        )
        validator = SchemaValidator(config)

        op = WriteOperation(
            operation="insert",
            entity_type="Sample",
            data={
                "id": "123",
                "name": "Test Entity",
                "age": 25,
                "score": 98.5,
                "active": True,
                "created_at": "2024-01-15T10:30:00Z",
                "status": "active",
                "owner": "user-1",
            },
        )
        result = validator.validate(op)

        assert result.is_valid is True
        assert len(result.errors) == 0
        assert result.entity_id == "123"
