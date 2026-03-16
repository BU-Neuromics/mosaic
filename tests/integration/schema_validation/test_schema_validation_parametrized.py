"""Parametrized integration tests for schema validation across multiple entity types.

These tests use pytest parametrization to verify validation behavior
across different entity types with varying schema definitions.
"""

import pytest

from hippo.core.exceptions import ValidationFailure


@pytest.fixture
def entity_type_fixtures(sample_schemas):
    """Provide entity type configurations for parametrized tests."""
    return {
        "sample": {
            "schema": sample_schemas["sample"],
            "valid_data": {
                "id": "param-sample-001",
                "name": "Param Test Sample",
                "quantity": 10,
            },
            "required_fields": ["id", "name", "quantity"],
        },
        "project": {
            "schema": sample_schemas["project"],
            "valid_data": {
                "id": "param-project-001",
                "name": "Param Test Project",
                "status": "active",
            },
            "required_fields": ["id", "name", "status"],
        },
    }


class TestRequiredFieldValidationParametrized:
    """Parametrized tests for required field validation across entity types."""

    @pytest.mark.parametrize("entity_type", ["sample", "project"])
    def test_valid_data_succeeds(
        self, hippo_client_with_validation, entity_type, entity_type_fixtures
    ):
        """Given valid data for an entity type, when creating an entity,
        then the operation should succeed."""
        fixture = entity_type_fixtures[entity_type]
        result = hippo_client_with_validation.create(entity_type, fixture["valid_data"])
        assert result["id"] == fixture["valid_data"]["id"]

    @pytest.mark.parametrize("entity_type", ["sample", "project"])
    def test_missing_all_required_fields_fails(
        self, hippo_client_with_validation, entity_type
    ):
        """Given data missing all required fields, when creating an entity,
        then the operation should fail."""
        data = {"id": "param-empty"}
        with pytest.raises(ValidationFailure):
            hippo_client_with_validation.create(entity_type, data)


class TestDataTypeValidationParametrized:
    """Parametrized tests for data type validation across entity types."""

    @pytest.mark.parametrize(
        "entity_type,invalid_field,invalid_value,expected_type",
        [
            ("sample", "name", 123, "string"),
            ("sample", "quantity", "not-a-number", "integer"),
            ("project", "name", 999, "string"),
            ("project", "status", 123, "string"),
        ],
    )
    def test_invalid_data_type_fails(
        self,
        hippo_client_with_validation,
        entity_type,
        invalid_field,
        invalid_value,
        expected_type,
        entity_type_fixtures,
    ):
        """Given invalid data type for a field, when creating an entity,
        then the operation should fail with appropriate error."""
        fixture = entity_type_fixtures[entity_type]
        data = fixture["valid_data"].copy()
        data[invalid_field] = invalid_value
        with pytest.raises(ValidationFailure) as exc_info:
            hippo_client_with_validation.create(entity_type, data)
        error_msg = str(exc_info.value)
        assert invalid_field in error_msg.lower()
        assert expected_type in error_msg.lower()


class TestForeignKeyValidationParametrized:
    """Parametrized tests for foreign key validation."""

    @pytest.mark.parametrize("entity_type", ["sample_with_reference"])
    def test_valid_reference_succeeds(
        self,
        hippo_client_with_validation,
        in_memory_storage,
        valid_project_data,
        entity_type,
    ):
        """Given valid foreign key reference, when creating an entity,
        then the operation should succeed."""
        in_memory_storage.insert("project", valid_project_data)
        data = {
            "id": "param-ref-001",
            "project_id": valid_project_data["id"],
            "name": "Test",
        }
        result = hippo_client_with_validation.create(entity_type, data)
        assert result["id"] == data["id"]

    @pytest.mark.parametrize("entity_type", ["sample_with_reference"])
    def test_invalid_reference_fails(
        self,
        hippo_client_with_validation,
        entity_type,
    ):
        """Given invalid foreign key reference, when creating an entity,
        then the operation should fail."""
        data = {
            "id": "param-ref-002",
            "project_id": "does-not-exist",
            "name": "Test",
        }
        with pytest.raises(ValidationFailure) as exc_info:
            hippo_client_with_validation.create(entity_type, data)
        error_msg = str(exc_info.value)
        assert "project" in error_msg.lower()


class TestMultipleEntityTypesIntegration:
    """Integration tests involving multiple entity types."""

    def test_create_related_entities(
        self,
        hippo_client_with_validation,
        in_memory_storage,
    ):
        """Given related entities, when creating them in order,
        then both should succeed."""
        project_data = {
            "id": "multi-project-001",
            "name": "Multi Entity Project",
            "status": "active",
        }
        project_result = hippo_client_with_validation.create("project", project_data)
        assert project_result["id"] == project_data["id"]

        sample_data = {
            "id": "multi-sample-001",
            "project_id": project_data["id"],
            "name": "Sample in Project",
        }
        sample_result = hippo_client_with_validation.create(
            "sample_with_reference", sample_data
        )
        assert sample_result["id"] == sample_data["id"]

        stored_project = in_memory_storage.get("project", project_data["id"])
        stored_sample = in_memory_storage.get(
            "sample_with_reference", sample_data["id"]
        )
        assert stored_project is not None
        assert stored_sample is not None

    def test_cascade_validation(
        self,
        hippo_client_with_validation,
    ):
        """Given multiple entities with validation, when each is validated independently,
        then each should behave according to its schema."""
        sample_data = {
            "id": "cascade-sample",
            "name": "Sample Entity",
            "quantity": 100,
        }
        result = hippo_client_with_validation.create("sample", sample_data)
        assert result["id"] == sample_data["id"]

        project_data = {
            "id": "cascade-project",
            "name": "Project Entity",
            "status": "active",
        }
        result2 = hippo_client_with_validation.create("project", project_data)
        assert result2["id"] == project_data["id"]
