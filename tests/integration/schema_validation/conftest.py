"""Pytest configuration and fixtures for schema validation integration tests."""

import sqlite3
from contextlib import contextmanager
from typing import Any
from unittest.mock import MagicMock

import pytest

from hippo.config.models import FieldDefinition, SchemaConfig
from hippo.core.client import HippoClient
from hippo.core.exceptions import ValidationFailure
from hippo.core.pipeline import ValidationPipeline
from hippo.core.validation.schema_validator import (
    SchemaValidationConfig,
    SchemaValidator,
)


class InMemoryStorage:
    """In-memory storage implementation using SQLite for integration tests."""

    def __init__(self):
        self._conn = sqlite3.connect(":memory:", check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._entities: dict[str, dict[str, Any]] = {}

    def close(self):
        """Close the database connection."""
        self._conn.close()

    @contextmanager
    def get_connection(self):
        """Get a database connection."""
        try:
            yield self._conn
        finally:
            pass

    def create_table(self, entity_type: str, fields: list[FieldDefinition]):
        """Create a table for the entity type."""
        if not fields:
            return
        field_defs = ["id TEXT PRIMARY KEY"]
        for field in fields:
            if field.name == "id":
                continue
            if field.type == "string":
                field_defs.append(f"{field.name} TEXT")
            elif field.type in ("integer", "float"):
                field_defs.append(f"{field.name} REAL")
            elif field.type == "boolean":
                field_defs.append(f"{field.name} INTEGER")
            elif field.type in ("date", "datetime"):
                field_defs.append(f"{field.name} TEXT")
            elif field.type == "list":
                field_defs.append(f"{field.name} TEXT")
            elif field.type == "dict":
                field_defs.append(f"{field.name} TEXT")
            else:
                field_defs.append(f"{field.name} TEXT")

        sql = f"CREATE TABLE IF NOT EXISTS {entity_type} ({', '.join(field_defs)})"
        self._conn.execute(sql)
        self._conn.commit()

    def insert(self, entity_type: str, data: dict[str, Any]) -> dict[str, Any]:
        """Insert an entity."""
        key = f"{entity_type}:{data.get('id')}"
        self._entities[key] = data.copy()
        return data

    def update(
        self, entity_type: str, entity_id: str, data: dict[str, Any]
    ) -> dict[str, Any]:
        """Update an entity."""
        key = f"{entity_type}:{entity_id}"
        if key in self._entities:
            self._entities[key].update(data)
            return self._entities[key]
        return data

    def get(self, entity_type: str, entity_id: str) -> dict[str, Any] | None:
        """Get an entity by ID."""
        key = f"{entity_type}:{entity_id}"
        return self._entities.get(key)

    def exists(self, entity_type: str, entity_id: str) -> bool:
        """Check if an entity exists."""
        key = f"{entity_type}:{entity_id}"
        return key in self._entities

    def list_all(self, entity_type: str) -> list[dict[str, Any]]:
        """List all entities of a type."""
        prefix = f"{entity_type}:"
        return [v for k, v in self._entities.items() if k.startswith(prefix)]


@pytest.fixture
def in_memory_storage():
    """Create an in-memory SQLite storage for testing."""
    storage = InMemoryStorage()
    yield storage
    storage.close()


@pytest.fixture
def sample_schemas():
    """Sample schemas for testing."""
    return {
        "sample": SchemaConfig(
            name="sample",
            version="1.0.0",
            fields=[
                FieldDefinition(
                    name="id", type="string", required=True, primary_key=True
                ),
                FieldDefinition(name="name", type="string", required=True),
                FieldDefinition(name="description", type="string", required=False),
                FieldDefinition(name="quantity", type="integer", required=True),
                FieldDefinition(name="price", type="float", required=False),
                FieldDefinition(name="is_active", type="boolean", required=False),
                FieldDefinition(name="tags", type="list", required=False),
                FieldDefinition(name="metadata", type="dict", required=False),
            ],
        ),
        "project": SchemaConfig(
            name="project",
            version="1.0.0",
            fields=[
                FieldDefinition(
                    name="id", type="string", required=True, primary_key=True
                ),
                FieldDefinition(name="name", type="string", required=True, unique=True),
                FieldDefinition(name="status", type="string", required=True),
            ],
        ),
        "sample_with_reference": SchemaConfig(
            name="sample_with_reference",
            version="1.0.0",
            fields=[
                FieldDefinition(
                    name="id", type="string", required=True, primary_key=True
                ),
                FieldDefinition(
                    name="project_id",
                    type="string",
                    required=True,
                    references={"entity_type": "project"},
                ),
                FieldDefinition(name="name", type="string", required=True),
            ],
        ),
        "sample_with_constraints": SchemaConfig(
            name="sample_with_constraints",
            version="1.0.0",
            fields=[
                FieldDefinition(
                    name="id", type="string", required=True, primary_key=True
                ),
                FieldDefinition(name="short_code", type="string", required=True),
                FieldDefinition(name="tags", type="list", required=False),
            ],
        ),
    }


@pytest.fixture
def hippo_client_with_validation(sample_schemas, in_memory_storage):
    """Create a HippoClient with schema validation enabled."""

    def entity_exists_fn(entity_type: str, entity_id: str) -> bool:
        return in_memory_storage.exists(entity_type, entity_id)

    schema_config = SchemaValidationConfig(
        schemas=sample_schemas,
        entity_exists_fn=entity_exists_fn,
    )
    validator = SchemaValidator(config=schema_config)
    pipeline = ValidationPipeline()
    pipeline.add_validator(validator)

    class ValidatedHippoClient(HippoClient):
        def __init__(self, storage, pipeline):
            super().__init__(pipeline=pipeline)
            self._storage = storage
            self._pipeline = pipeline

        def _create_internal(
            self, entity_type: str, data: dict[str, Any]
        ) -> dict[str, Any]:
            schema = sample_schemas.get(entity_type)
            if schema:
                self._storage.create_table(entity_type, schema.fields)
            return self._storage.insert(entity_type, data)

        def _update_internal(
            self, entity_type: str, entity_id: str, data: dict[str, Any]
        ) -> dict[str, Any]:
            return self._storage.update(entity_type, entity_id, data)

        def _delete_internal(self, entity_type: str, entity_id: str) -> bool:
            key = f"{entity_type}:{entity_id}"
            if key in self._storage._entities:
                del self._storage._entities[key]
                return True
            return False

    client = ValidatedHippoClient(in_memory_storage, pipeline)
    return client


@pytest.fixture
def hippo_client_without_validation():
    """Create a HippoClient without validation (for baseline tests)."""
    return HippoClient(bypass_validation=True)


@pytest.fixture
def valid_sample_data():
    """Valid data for sample entity."""
    return {
        "id": "sample-001",
        "name": "Test Sample",
        "description": "A test sample",
        "quantity": 42,
        "price": 19.99,
        "is_active": True,
        "tags": ["test", "sample"],
        "metadata": {"key": "value"},
    }


@pytest.fixture
def valid_project_data():
    """Valid data for project entity."""
    return {
        "id": "project-001",
        "name": "Test Project",
        "status": "active",
    }


@pytest.fixture
def sample_with_reference_data(valid_project_data):
    """Valid data for sample with reference."""
    return {
        "id": "sample-ref-001",
        "project_id": valid_project_data["id"],
        "name": "Sample with Project Reference",
    }
