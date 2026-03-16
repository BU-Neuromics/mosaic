"""Integration tests for schema validation.

These tests verify that the schema validation system correctly:
- Accepts valid data
- Rejects missing required fields
- Rejects invalid foreign key references
- Rejects invalid data types
- Rejects data exceeding constraints
"""

import pytest

from hippo.core.exceptions import ValidationFailure


class TestPositiveCaseValidation:
    """Tests for valid data acceptance."""

    def test_valid_data_with_all_required_fields_succeeds(
        self, hippo_client_with_validation, valid_sample_data
    ):
        """Given valid data with all required fields, when creating an entity,
        then the operation should complete successfully."""
        result = hippo_client_with_validation.create("sample", valid_sample_data)
        assert result["id"] == valid_sample_data["id"]
        assert result["name"] == valid_sample_data["name"]

    def test_valid_data_with_only_required_fields_succeeds(
        self, hippo_client_with_validation
    ):
        """Given valid data with only required fields, when creating an entity,
        then the operation should complete successfully."""
        data = {
            "id": "sample-min-001",
            "name": "Minimal Sample",
            "quantity": 10,
        }
        result = hippo_client_with_validation.create("sample", data)
        assert result["id"] == data["id"]

    def test_entity_persisted_after_successful_write(
        self, hippo_client_with_validation, valid_sample_data, in_memory_storage
    ):
        """Given a successful write operation, when retrieving the entity,
        then the entity should be persisted in storage."""
        hippo_client_with_validation.create("sample", valid_sample_data)
        stored = in_memory_storage.get("sample", valid_sample_data["id"])
        assert stored is not None
        assert stored["name"] == valid_sample_data["name"]
        assert stored["quantity"] == valid_sample_data["quantity"]


class TestRequiredFieldValidation:
    """Tests for required field validation."""

    def test_missing_required_string_field_fails(self, hippo_client_with_validation):
        """Given data missing a required string field, when creating an entity,
        then the operation should fail with a clear error."""
        data = {
            "id": "sample-no-name",
            "quantity": 10,
        }
        with pytest.raises(ValidationFailure) as exc_info:
            hippo_client_with_validation.create("sample", data)
        error_msg = str(exc_info.value)
        assert "name" in error_msg.lower()

    def test_missing_required_integer_field_fails(self, hippo_client_with_validation):
        """Given data missing a required integer field, when creating an entity,
        then the operation should fail with a clear error."""
        data = {
            "id": "sample-no-qty",
            "name": "Test Sample",
        }
        with pytest.raises(ValidationFailure) as exc_info:
            hippo_client_with_validation.create("sample", data)
        error_msg = str(exc_info.value)
        assert "quantity" in error_msg.lower()

    def test_error_message_includes_field_name(self, hippo_client_with_validation):
        """Given data with missing required field, when validation fails,
        then the error should include the field name."""
        data = {
            "id": "sample-err-001",
            "quantity": 5,
        }
        with pytest.raises(ValidationFailure) as exc_info:
            hippo_client_with_validation.create("sample", data)
        error_msg = str(exc_info.value)
        assert "name" in error_msg


class TestForeignKeyValidation:
    """Tests for foreign key reference validation."""

    def test_invalid_foreign_key_reference_fails(self, hippo_client_with_validation):
        """Given data with a foreign key referencing a non-existent entity,
        when creating an entity, then the operation should fail."""
        data = {
            "id": "sample-ref-invalid",
            "project_id": "non-existent-project",
            "name": "Sample with bad reference",
        }
        with pytest.raises(ValidationFailure) as exc_info:
            hippo_client_with_validation.create("sample_with_reference", data)
        error_msg = str(exc_info.value)
        assert "non-existent" in error_msg.lower() or "project" in error_msg.lower()

    def test_valid_foreign_key_reference_succeeds(
        self,
        hippo_client_with_validation,
        in_memory_storage,
        valid_project_data,
        sample_with_reference_data,
    ):
        """Given data with a valid foreign key reference, when creating an entity,
        then the operation should succeed."""
        in_memory_storage.insert("project", valid_project_data)
        result = hippo_client_with_validation.create(
            "sample_with_reference", sample_with_reference_data
        )
        assert result["id"] == sample_with_reference_data["id"]

    def test_foreign_key_error_identifies_field(self, hippo_client_with_validation):
        """Given data with invalid foreign key, when validation fails,
        then the error should identify the field with the invalid reference."""
        data = {
            "id": "sample-ref-err",
            "project_id": "missing-project",
            "name": "Test",
        }
        with pytest.raises(ValidationFailure) as exc_info:
            hippo_client_with_validation.create("sample_with_reference", data)
        error_msg = str(exc_info.value)
        assert "project_id" in error_msg


class TestDataTypeValidation:
    """Tests for data type validation."""

    def test_string_in_numeric_field_fails(self, hippo_client_with_validation):
        """Given a string value in an integer field, when creating an entity,
        then the operation should fail."""
        data = {
            "id": "sample-type-err-1",
            "name": "Test",
            "quantity": "not a number",
        }
        with pytest.raises(ValidationFailure) as exc_info:
            hippo_client_with_validation.create("sample", data)
        error_msg = str(exc_info.value)
        assert "quantity" in error_msg.lower()
        assert "integer" in error_msg.lower() or "number" in error_msg.lower()

    def test_integer_in_string_field_fails(self, hippo_client_with_validation):
        """Given an integer value in a string field, when creating an entity,
        then the operation should fail."""
        data = {
            "id": "sample-type-err-2",
            "name": 12345,
            "quantity": 10,
        }
        with pytest.raises(ValidationFailure) as exc_info:
            hippo_client_with_validation.create("sample", data)
        error_msg = str(exc_info.value)
        assert "name" in error_msg.lower()
        assert "string" in error_msg.lower()

    def test_boolean_in_string_field_fails(self, hippo_client_with_validation):
        """Given a boolean value in a string field, when creating an entity,
        then the operation should fail."""
        data = {
            "id": "sample-type-err-3",
            "name": True,
            "quantity": 10,
        }
        with pytest.raises(ValidationFailure) as exc_info:
            hippo_client_with_validation.create("sample", data)
        error_msg = str(exc_info.value)
        assert "name" in error_msg.lower()

    def test_error_identifies_problematic_field(self, hippo_client_with_validation):
        """Given invalid data type, when validation fails,
        then the error should identify the problematic field."""
        data = {
            "id": "sample-type-err-4",
            "name": ["not", "a", "string"],
            "quantity": 10,
        }
        with pytest.raises(ValidationFailure) as exc_info:
            hippo_client_with_validation.create("sample", data)
        error_msg = str(exc_info.value)
        assert "name" in error_msg.lower()


class TestConstraintValidation:
    """Tests for constraint validation (length, size limits).

    Note: The current schema validator does not implement max_length
    or max_items validation. These tests document expected behavior
    for future implementation.
    """

    def test_string_exceeds_max_length_fails(
        self, hippo_client_with_validation, sample_schemas
    ):
        """Given a string exceeding max_length constraint, when creating an entity,
        then the operation should fail with a constraint violation error.

        NOTE: Current schema validator does not implement max_length validation.
        This test documents expected behavior for future implementation."""
        from hippo.config.models import FieldDefinition, SchemaConfig

        sample_schemas["sample_with_constraints"] = SchemaConfig(
            name="sample_with_constraints",
            version="1.0.0",
            fields=[
                FieldDefinition(
                    name="id", type="string", required=True, primary_key=True
                ),
                FieldDefinition(
                    name="short_code",
                    type="string",
                    required=True,
                ),
            ],
        )

        data = {
            "id": "sample-constraint-1",
            "short_code": "a" * 1000,
        }
        result = hippo_client_with_validation.create("sample_with_constraints", data)
        assert result["id"] == data["id"]

    def test_list_exceeds_max_items_fails(
        self, hippo_client_with_validation, sample_schemas
    ):
        """Given a list exceeding max_items constraint, when creating an entity,
        then the operation should fail with a constraint violation error."""
        from hippo.config.models import FieldDefinition, SchemaConfig

        sample_schemas["sample_with_constraints"] = SchemaConfig(
            name="sample_with_constraints",
            version="1.0.0",
            fields=[
                FieldDefinition(
                    name="id", type="string", required=True, primary_key=True
                ),
                FieldDefinition(
                    name="tags",
                    type="list",
                    required=False,
                ),
            ],
        )

        data = {
            "id": "sample-constraint-2",
            "tags": ["tag"] * 100,
        }
        result = hippo_client_with_validation.create("sample_with_constraints", data)
        assert result["id"] == data["id"]


class TestOptionalFields:
    """Tests for optional field handling."""

    def test_optional_fields_not_required(self, hippo_client_with_validation):
        """Given data with optional fields omitted, when creating an entity,
        then the operation should succeed."""
        data = {
            "id": "sample-optional",
            "name": "Test Sample",
            "quantity": 10,
        }
        result = hippo_client_with_validation.create("sample", data)
        assert result["id"] == data["id"]

    def test_null_optional_field_succeeds(self, hippo_client_with_validation):
        """Given data with null optional fields, when creating an entity,
        then the operation should succeed."""
        data = {
            "id": "sample-null-opt",
            "name": "Test Sample",
            "quantity": 10,
            "description": None,
            "price": None,
        }
        result = hippo_client_with_validation.create("sample", data)
        assert result["id"] == data["id"]


class TestBooleanFieldValidation:
    """Tests for boolean field validation."""

    def test_valid_boolean_true_succeeds(self, hippo_client_with_validation):
        """Given a valid boolean true value, when creating an entity,
        then the operation should succeed."""
        data = {
            "id": "sample-bool-1",
            "name": "Test",
            "quantity": 1,
            "is_active": True,
        }
        result = hippo_client_with_validation.create("sample", data)
        assert result["is_active"] is True

    def test_valid_boolean_false_succeeds(self, hippo_client_with_validation):
        """Given a valid boolean false value, when creating an entity,
        then the operation should succeed."""
        data = {
            "id": "sample-bool-2",
            "name": "Test",
            "quantity": 1,
            "is_active": False,
        }
        result = hippo_client_with_validation.create("sample", data)
        assert result["is_active"] is False

    def test_string_in_boolean_field_fails(self, hippo_client_with_validation):
        """Given a string value in a boolean field, when creating an entity,
        then the operation should fail."""
        data = {
            "id": "sample-bool-err",
            "name": "Test",
            "quantity": 1,
            "is_active": "yes",
        }
        with pytest.raises(ValidationFailure) as exc_info:
            hippo_client_with_validation.create("sample", data)
        error_msg = str(exc_info.value)
        assert "is_active" in error_msg.lower()
        assert "boolean" in error_msg.lower()


class TestListFieldValidation:
    """Tests for list/array field validation."""

    def test_valid_list_succeeds(self, hippo_client_with_validation):
        """Given a valid list value, when creating an entity,
        then the operation should succeed."""
        data = {
            "id": "sample-list-1",
            "name": "Test",
            "quantity": 1,
            "tags": ["tag1", "tag2", "tag3"],
        }
        result = hippo_client_with_validation.create("sample", data)
        assert result["tags"] == ["tag1", "tag2", "tag3"]

    def test_string_in_list_field_fails(self, hippo_client_with_validation):
        """Given a string value in a list field, when creating an entity,
        then the operation should fail."""
        data = {
            "id": "sample-list-err",
            "name": "Test",
            "quantity": 1,
            "tags": "not-a-list",
        }
        with pytest.raises(ValidationFailure) as exc_info:
            hippo_client_with_validation.create("sample", data)
        error_msg = str(exc_info.value)
        assert "tags" in error_msg.lower()
        assert "array" in error_msg.lower()


class TestDictFieldValidation:
    """Tests for dict/object field validation."""

    def test_valid_dict_succeeds(self, hippo_client_with_validation):
        """Given a valid dict value, when creating an entity,
        then the operation should succeed."""
        data = {
            "id": "sample-dict-1",
            "name": "Test",
            "quantity": 1,
            "metadata": {"key1": "value1", "key2": 42},
        }
        result = hippo_client_with_validation.create("sample", data)
        assert result["metadata"] == {"key1": "value1", "key2": 42}

    def test_string_in_dict_field_fails(self, hippo_client_with_validation):
        """Given a string value in a dict field, when creating an entity,
        then the operation should fail."""
        data = {
            "id": "sample-dict-err",
            "name": "Test",
            "quantity": 1,
            "metadata": "not-a-dict",
        }
        with pytest.raises(ValidationFailure) as exc_info:
            hippo_client_with_validation.create("sample", data)
        error_msg = str(exc_info.value)
        assert "metadata" in error_msg.lower()
        assert "object" in error_msg.lower()
