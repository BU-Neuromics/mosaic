"""Integration tests for PostgreSQL storage adapter.

Requires a running PostgreSQL instance. Set HIPPO_DATABASE_URL to connect:

    HIPPO_DATABASE_URL=postgresql://hippo_test:hippo_test@localhost:5433/hippo_test pytest tests/integration/test_postgres_adapter.py

Use docker-compose.test.yml to start a test PostgreSQL instance:

    docker compose -f docker-compose.test.yml up -d
"""

import json
import os
import uuid

import pytest

# Skip all tests if psycopg is not installed or no database URL is set
psycopg = pytest.importorskip("psycopg")

POSTGRES_URL = os.environ.get("HIPPO_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not POSTGRES_URL,
    reason="HIPPO_DATABASE_URL not set — skipping PostgreSQL tests",
)


@pytest.fixture
def adapter():
    """Create a fresh PostgresAdapter with clean tables for each test."""
    from hippo.core.storage.adapters.postgres_adapter import PostgresAdapter

    db_url = POSTGRES_URL
    # Use a unique schema prefix to avoid cross-test contamination
    adapter = PostgresAdapter(database_url=db_url, min_pool_size=1, max_pool_size=5)

    yield adapter

    # Cleanup: drop all test data
    with adapter._transaction() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM entity_external_ids")
        cur.execute("DELETE FROM relationships")
        # Disable provenance triggers temporarily for cleanup
        cur.execute("ALTER TABLE provenance DISABLE TRIGGER ALL")
        cur.execute("DELETE FROM provenance")
        cur.execute("ALTER TABLE provenance ENABLE TRIGGER ALL")
        cur.execute("DELETE FROM entities")
        # Drop any FTS tables
        cur.execute(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'public' AND tablename LIKE 'fts_%'"
        )
        for row in cur.fetchall():
            cur.execute(f'DROP TABLE IF EXISTS "{row["tablename"]}" CASCADE')

    adapter.close()


@pytest.fixture
def sample_entity():
    """Create a sample entity for testing."""
    from hippo.core.storage.adapters.postgres_adapter import PostgresEntity

    return PostgresEntity(
        id=str(uuid.uuid4()),
        entity_type="Sample",
        is_available=True,
        version=1,
        data={"name": "Test Sample", "category": "tissue", "status": "active"},
        created_at=None,
        updated_at=None,
    )


class TestPostgresAdapterCRUD:
    """Test basic CRUD operations."""

    def test_create_entity(self, adapter, sample_entity):
        result = adapter.create(sample_entity)
        assert result is not None
        assert result.id == sample_entity.id

    def test_read_entity(self, adapter, sample_entity):
        adapter.create(sample_entity)
        result = adapter.read(sample_entity.id)
        assert result is not None
        assert result.id == sample_entity.id
        assert result.entity_type == "Sample"
        assert result.data["name"] == "Test Sample"

    def test_read_nonexistent_entity(self, adapter):
        result = adapter.read("nonexistent-id")
        assert result is None

    def test_update_entity(self, adapter, sample_entity):
        adapter.create(sample_entity)
        result = adapter.update(sample_entity)
        assert result is not None
        assert result.id == sample_entity.id

    def test_delete_entity(self, adapter, sample_entity):
        adapter.create(sample_entity)
        result = adapter.delete(sample_entity.id)
        assert result is True
        # Should not be readable after soft delete
        assert adapter.read(sample_entity.id) is None

    def test_delete_nonexistent_entity(self, adapter):
        result = adapter.delete("nonexistent-id")
        assert result is False

    def test_read_any_returns_deleted(self, adapter, sample_entity):
        adapter.create(sample_entity)
        adapter.delete(sample_entity.id)
        result = adapter.read_any(sample_entity.id)
        assert result is not None
        assert result.is_available is False


class TestPostgresAdapterQuery:
    """Test query operations."""

    def test_find_all(self, adapter, sample_entity):
        adapter.create(sample_entity)
        results = list(adapter.findAll())
        assert len(results) >= 1
        ids = [r.id for r in results]
        assert sample_entity.id in ids

    def test_find_by_entity_type(self, adapter, sample_entity):
        from hippo.core.storage import Query

        adapter.create(sample_entity)
        query = Query(entity_type="Sample")
        results = list(adapter.find(query))
        assert len(results) >= 1
        assert all(r.entity_type == "Sample" for r in results)

    def test_find_by_field_filter(self, adapter, sample_entity):
        adapter.create(sample_entity)
        results = list(adapter.findBy(category="tissue"))
        assert len(results) >= 1

    def test_find_with_or_filter(self, adapter):
        from hippo.core.storage import Query
        from hippo.core.storage.adapters.postgres_adapter import PostgresEntity

        e1 = PostgresEntity(
            id=str(uuid.uuid4()),
            entity_type="Sample",
            is_available=True,
            version=1,
            data={"name": "Alpha", "category": "blood"},
            created_at=None,
            updated_at=None,
        )
        e2 = PostgresEntity(
            id=str(uuid.uuid4()),
            entity_type="Sample",
            is_available=True,
            version=1,
            data={"name": "Beta", "category": "tissue"},
            created_at=None,
            updated_at=None,
        )
        adapter.create(e1)
        adapter.create(e2)

        query = Query(
            entity_type="Sample",
            filters=[{"category": "blood"}, {"category": "tissue"}],
            filter_mode="or",
        )
        results = list(adapter.find(query))
        assert len(results) >= 2

    def test_find_with_limit_offset(self, adapter):
        from hippo.core.storage import Query
        from hippo.core.storage.adapters.postgres_adapter import PostgresEntity

        for i in range(5):
            e = PostgresEntity(
                id=str(uuid.uuid4()),
                entity_type="Sample",
                is_available=True,
                version=1,
                data={"name": f"Sample-{i}"},
                created_at=None,
                updated_at=None,
            )
            adapter.create(e)

        query = Query(entity_type="Sample", limit=2, offset=1)
        results = list(adapter.find(query))
        assert len(results) == 2


class TestPostgresAdapterFTS:
    """Test full-text search functionality."""

    def test_create_fts_table(self, adapter):
        adapter.create_fts_table("fts_sample_name", ["entity_id", "content"])
        tables = adapter.get_fts_tables_for_entity_type("sample")
        assert "fts_sample_name" in tables

    def test_search_entities(self, adapter, sample_entity):
        from hippo.core.storage.adapters.postgres_adapter import PostgresFTSStore

        adapter.create(sample_entity)
        adapter.create_fts_table("fts_sample_name", ["entity_id", "content"])

        with adapter._transaction() as conn:
            fts = PostgresFTSStore(conn)
            fts.sync_entity_to_fts(
                "fts_sample_name", sample_entity.id, "Test Sample tissue"
            )

        results = adapter.search(
            query="tissue",
            entity_type="Sample",
            field_name="name",
        )
        assert len(results) >= 1
        assert results[0].entity_id == sample_entity.id
        assert results[0].score > 0

    def test_search_nonexistent_fts_table(self, adapter):
        from hippo.core.exceptions import SearchCapabilityError

        with pytest.raises(SearchCapabilityError):
            adapter.search(
                query="test",
                entity_type="Nonexistent",
                field_name="name",
            )

    def test_search_capabilities(self, adapter):
        caps = adapter.search_capabilities()
        assert "fts" in caps
        assert "trigram" in caps


class TestPostgresAdapterProvenance:
    """Test provenance tracking."""

    def test_create_records_provenance(self, adapter, sample_entity):
        adapter.create(sample_entity)
        history = adapter.history(sample_entity.id)
        assert len(history) >= 1
        assert history[0]["operation_type"] == "CREATE"

    def test_delete_records_provenance(self, adapter, sample_entity):
        adapter.create(sample_entity)
        adapter.delete(sample_entity.id)
        history = adapter.history(sample_entity.id)
        assert len(history) >= 2
        ops = [h["operation_type"] for h in history]
        assert "CREATE" in ops
        assert "SOFT_DELETE" in ops

    def test_track_creation(self, adapter, sample_entity):
        record = adapter.track_creation(sample_entity, {"test": "metadata"})
        assert record.operation == "create"
        assert record.source == "postgres_adapter"

    def test_track_update(self, adapter, sample_entity):
        record = adapter.track_update(sample_entity, {"test": "metadata"})
        assert record.operation == "update"

    def test_track_deletion(self, adapter, sample_entity):
        record = adapter.track_deletion(sample_entity.id, {"test": "metadata"})
        assert record.operation == "delete"


class TestPostgresAdapterAtomicUpsert:
    """Test atomic upsert behavior for multi-instance safety."""

    def test_create_same_entity_twice_upserts(self, adapter, sample_entity):
        adapter.create(sample_entity)
        # Second create should upsert, not fail
        sample_entity.data["name"] = "Updated Name"
        adapter.create(sample_entity)

        result = adapter.read(sample_entity.id)
        assert result is not None


class TestPostgresAdapterRelationships:
    """Test relationship operations."""

    def test_create_and_find_relationship(self, adapter):
        from hippo.core.storage.adapters.postgres_adapter import (
            PostgresEntity,
            PostgresRelationshipStore,
        )

        e1 = PostgresEntity(
            id=str(uuid.uuid4()),
            entity_type="Sample",
            is_available=True,
            version=1,
            data={"name": "Parent"},
            created_at=None,
            updated_at=None,
        )
        e2 = PostgresEntity(
            id=str(uuid.uuid4()),
            entity_type="Sample",
            is_available=True,
            version=1,
            data={"name": "Child"},
            created_at=None,
            updated_at=None,
        )
        adapter.create(e1)
        adapter.create(e2)

        with adapter._transaction() as conn:
            rel_store = PostgresRelationshipStore(conn)
            rel = rel_store.create(
                source_id=e1.id,
                target_id=e2.id,
                relationship_type="parent_of",
            )
            assert rel.source_id == e1.id

            results = list(rel_store.find_by_source(e1.id))
            assert len(results) >= 1


class TestPostgresAdapterExternalIds:
    """Test external ID operations."""

    def test_create_and_lookup_external_id(self, adapter, sample_entity):
        from hippo.core.storage.adapters.postgres_adapter import PostgresExternalIdStore

        adapter.create(sample_entity)

        with adapter._transaction() as conn:
            eid_store = PostgresExternalIdStore(conn)
            record = eid_store.create_external_id(sample_entity.id, "EXT-001")
            assert record.external_id == "EXT-001"

            found = eid_store.get_entity_by_external_id("EXT-001")
            assert found is not None
            assert found.entity_id == sample_entity.id
