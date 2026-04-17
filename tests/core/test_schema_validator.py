"""Tests for SchemaValidator backed by linkml.validator."""

import pytest

from hippo.core.validation import (
    SchemaValidationConfig,
    SchemaValidator,
    WriteOperation,
)
from tests.support.linkml_schemas import build_registry


SAMPLE_CLASSES = {
    "User": {"attributes": {"id": {"identifier": True}}},
    "Sample": {
        "attributes": {
            "id": {"identifier": True, "required": True},
            "name": {"range": "string", "required": True},
            "age": {"range": "integer"},
            "score": {"range": "float"},
            "active": {"range": "boolean"},
            "created_at": {"range": "datetime"},
            "status": {"range": "SampleStatus"},
            "owner": {"range": "User"},
        }
    },
}
SAMPLE_ENUMS = {
    "SampleStatus": {
        "permissible_values": {"active": {}, "archived": {}, "deleted": {}}
    }
}


def _validator(*, entity_exists_fn=None) -> SchemaValidator:
    registry = build_registry(SAMPLE_CLASSES, enums=SAMPLE_ENUMS)
    return SchemaValidator(
        SchemaValidationConfig(registry=registry, entity_exists_fn=entity_exists_fn)
    )


def _op(data):
    return WriteOperation(operation="insert", entity_type="Sample", data=data)


class TestRequiredFieldValidation:
    def test_missing_required_field_returns_error(self):
        result = _validator().validate(_op({"id": "123"}))
        assert result.is_valid is False
        assert any("'name'" in e and "required" in e for e in result.errors)
        assert result.entity_id == "123"

    def test_present_required_field_passes(self):
        result = _validator().validate(_op({"id": "123", "name": "Test"}))
        assert result.is_valid is True
        assert result.errors == []


class TestStringTypeValidation:
    def test_non_string_name_returns_error(self):
        result = _validator().validate(_op({"id": "123", "name": 123}))
        assert result.is_valid is False
        assert any("not of type" in e and "string" in e for e in result.errors)

    def test_valid_string_passes(self):
        result = _validator().validate(_op({"id": "123", "name": "test"}))
        assert result.is_valid is True


class TestNumberTypeValidation:
    def test_non_integer_age_returns_error(self):
        result = _validator().validate(
            _op({"id": "123", "name": "test", "age": "not a number"})
        )
        assert result.is_valid is False
        assert any("not of type" in e for e in result.errors)

    def test_non_float_score_returns_error(self):
        result = _validator().validate(
            _op({"id": "123", "name": "test", "score": "not a float"})
        )
        assert result.is_valid is False
        assert any("not of type" in e for e in result.errors)


class TestBooleanTypeValidation:
    def test_non_boolean_active_returns_error(self):
        result = _validator().validate(
            _op({"id": "123", "name": "test", "active": "yes"})
        )
        assert result.is_valid is False
        assert any("not of type" in e and "boolean" in e for e in result.errors)


class TestTimestampValidation:
    def test_valid_iso_timestamp_passes(self):
        result = _validator().validate(
            _op(
                {
                    "id": "123",
                    "name": "test",
                    "created_at": "2024-01-15T10:30:00Z",
                }
            )
        )
        assert result.is_valid is True


class TestEntityReferenceValidation:
    def test_non_existent_entity_reference_returns_error(self):
        validator = _validator(
            entity_exists_fn=lambda t, i: i in {"user-1", "user-2"}
        )
        result = validator.validate(
            _op({"id": "123", "name": "test", "owner": "user-999"})
        )
        assert result.is_valid is False
        assert any("User" in e and "user-999" in e for e in result.errors)

    def test_existing_entity_reference_passes(self):
        validator = _validator(
            entity_exists_fn=lambda t, i: i in {"user-1", "user-2"}
        )
        result = validator.validate(
            _op({"id": "123", "name": "test", "owner": "user-1"})
        )
        assert result.is_valid is True


class TestNestedReferenceValidation:
    def test_nested_object_reference_error(self):
        validator = _validator(
            entity_exists_fn=lambda t, i: i in {"user-1", "user-2"}
        )
        result = validator.validate(
            _op({"id": "123", "name": "test", "owner": {"id": "user-999"}})
        )
        assert result.is_valid is False


class TestEnumValidation:
    def test_invalid_enum_value_returns_error(self):
        result = _validator().validate(
            _op({"id": "123", "name": "test", "status": "invalid"})
        )
        assert result.is_valid is False
        assert any("not one of" in e for e in result.errors)

    def test_valid_enum_value_passes(self):
        result = _validator().validate(
            _op({"id": "123", "name": "test", "status": "active"})
        )
        assert result.is_valid is True


class TestValidWriteOperation:
    def test_valid_write_operation_passes(self):
        validator = _validator(
            entity_exists_fn=lambda t, i: i in {"user-1", "user-2"}
        )
        result = validator.validate(
            _op(
                {
                    "id": "123",
                    "name": "Test Entity",
                    "age": 25,
                    "score": 98.5,
                    "active": True,
                    "created_at": "2024-01-15T10:30:00Z",
                    "status": "active",
                    "owner": "user-1",
                }
            )
        )
        assert result.is_valid is True
        assert result.errors == []
        assert result.entity_id == "123"
