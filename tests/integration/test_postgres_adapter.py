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
def adapter(minimal_schema_registry):
    """Create a fresh PostgresAdapter with clean tables for each test."""
    from hippo.core.storage.adapters.postgres_adapter import PostgresAdapter

    db_url = POSTGRES_URL
    # Use a unique schema prefix to avoid cross-test contamination
    adapter = PostgresAdapter(database_url=db_url, schema_registry=minimal_schema_registry, min_pool_size=1, max_pool_size=5)

    yield adapter

    # Cleanup: drop all test data
    with adapter._transaction() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM entity_external_ids")
        cur.execute("DELETE FROM relationships")
        # Disable provenance triggers temporarily for cleanup. The table
        # was renamed from ``provenance`` to ``ProvenanceRecord`` per
        # sec9 §9.6 / Decision 9.6.D.
        cur.execute('ALTER TABLE "ProvenanceRecord" DISABLE TRIGGER ALL')
        cur.execute('DELETE FROM "ProvenanceRecord"')
        cur.execute('ALTER TABLE "ProvenanceRecord" ENABLE TRIGGER ALL')
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
        )
        e2 = PostgresEntity(
            id=str(uuid.uuid4()),
            entity_type="Sample",
            is_available=True,
            version=1,
            data={"name": "Beta", "category": "tissue"},
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
        # sec9 §9.6 Operation enum values (lowercase)
        assert history[0]["operation_type"] == "create"

    def test_delete_records_provenance(self, adapter, sample_entity):
        adapter.create(sample_entity)
        adapter.delete(sample_entity.id)
        history = adapter.history(sample_entity.id)
        assert len(history) >= 2
        ops = [h["operation_type"] for h in history]
        # Decision 9.6.B: SOFT_DELETE → availability_change
        assert "create" in ops
        assert "availability_change" in ops

    def test_track_creation(self, adapter, sample_entity):
        record = adapter.track_creation(sample_entity, {"test": "metadata"})
        assert record.operation == "create"

    def test_track_update(self, adapter, sample_entity):
        record = adapter.track_update(sample_entity, {"test": "metadata"})
        assert record.operation == "update"

    def test_track_deletion(self, adapter, sample_entity):
        record = adapter.track_deletion(sample_entity.id, {"test": "metadata"})
        # Legacy "delete" → availability_change per Decision 9.6.B
        assert record.operation == "availability_change"


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
        )
        e2 = PostgresEntity(
            id=str(uuid.uuid4()),
            entity_type="Sample",
            is_available=True,
            version=1,
            data={"name": "Child"},
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


class TestPostgresBatchPut:
    """Atomic multi-entity write over Postgres (issue #84 increment 2).

    Confirms ``HippoClient.batch_put`` is backend-agnostic: the Postgres
    adapter's ``staged_transaction`` drives the same all-or-nothing commit
    and intra-batch forward-reference resolution proven for SQLite.
    """

    @pytest.fixture
    def client(self, adapter):
        from hippo.core.client import HippoClient

        return HippoClient(storage=adapter)

    def test_commits_valid_set_atomically(self, client):
        from hippo.core.validation import WriteOperation

        ops = [
            WriteOperation(operation="insert", entity_type="Sample", data={"id": "pg-s1", "name": "a"}),
            WriteOperation(operation="insert", entity_type="Sample", data={"id": "pg-s2", "name": "b"}),
        ]
        result = client.batch_put(ops)
        assert result.committed is True
        assert client._storage.read("pg-s1") is not None
        assert client._storage.read("pg-s2") is not None

    def test_rollback_on_mid_batch_failure(self, client, monkeypatch):
        from hippo.core.validation import WriteOperation

        ops = [
            WriteOperation(operation="insert", entity_type="Sample", data={"id": "pg-r1", "name": "a"}),
            WriteOperation(operation="insert", entity_type="Sample", data={"id": "pg-r2", "name": "b"}),
        ]
        orig = client._put_internal
        calls = {"n": 0}

        def failing(entity_type, data, entity_id=None):
            calls["n"] += 1
            if calls["n"] == 2:
                raise RuntimeError("boom on second write")
            return orig(entity_type, data, entity_id)

        monkeypatch.setattr(client, "_put_internal", failing)
        with pytest.raises(RuntimeError, match="boom on second write"):
            client.batch_put(ops)

        assert client._storage.read("pg-r1") is None
        assert client._storage.read("pg-r2") is None

    def test_intra_batch_relationship_forward_reference(self, client):
        from hippo.core.validation import WriteOperation

        ops = [
            WriteOperation(operation="insert", entity_type="Donor", data={"id": "pg-donor", "name": "D"}),
            WriteOperation(operation="insert", entity_type="Sample", data={"id": "pg-sample", "name": "S"}),
        ]
        rels = [
            {"source_id": "pg-donor", "target_id": "pg-sample", "relationship_type": "donated"}
        ]
        result = client.batch_put(ops, relationships=rels)
        assert result.committed is True
        assert len(result.relationships) == 1
        assert client._storage.read("pg-donor") is not None
        assert client._storage.read("pg-sample") is not None


class TestPostgresClientFTSWrites:
    """Regression: client writes on postgres with hippo_search schemas.

    The first real DataHelix certification boot (datahelix#45) failed on
    every write: ``IngestionService._sync_entity_to_fts`` checked FTS-table
    existence with the SQLite helper (``sqlite_master`` + ``?`` placeholder),
    which psycopg rejects as "the query has 0 placeholders but 1 parameters
    were passed". The check must go through the adapter's own FTS store.
    """

    @pytest.fixture
    def fts_client(self):
        from hippo.core.client import HippoClient
        from hippo.core.storage.adapters.postgres_adapter import PostgresAdapter
        from tests.support.linkml_schemas import build_registry

        registry = build_registry(
            {
                "Sample": {
                    "attributes": {
                        "id": {"identifier": True},
                        "name": {"range": "string", "required": True},
                        "notes": {
                            "range": "string",
                            "annotations": {"hippo_search": "fts5"},
                        },
                    }
                }
            }
        )
        adapter = PostgresAdapter(
            database_url=POSTGRES_URL,
            schema_registry=registry,
            min_pool_size=1,
            max_pool_size=5,
        )
        client = HippoClient(storage=adapter, registry=registry)
        yield client
        with adapter._transaction() as conn:
            cur = conn.cursor()
            cur.execute('ALTER TABLE "ProvenanceRecord" DISABLE TRIGGER ALL')
            cur.execute('DELETE FROM "ProvenanceRecord"')
            cur.execute('ALTER TABLE "ProvenanceRecord" ENABLE TRIGGER ALL')
            cur.execute("DELETE FROM entities")
            cur.execute(
                "SELECT tablename FROM pg_tables "
                "WHERE schemaname = 'public' AND tablename LIKE 'fts_%'"
            )
            for row in cur.fetchall():
                cur.execute(f'DROP TABLE IF EXISTS "{row["tablename"]}" CASCADE')
        adapter.close()

    def test_put_succeeds_with_fts_schema(self, fts_client):
        created = fts_client.put(
            "Sample",
            {"id": str(uuid.uuid4()), "name": "n1", "notes": "searchable text"},
        )
        assert fts_client._storage.read(created["id"]) is not None

    def test_search_finds_seeded_content_on_fresh_deployment(self, fts_client):
        """No manual FTS-table creation: _init_database creates the shadow
        tables from the schema (parity with SQLite's typed-table DDL), the
        ingestion service syncs content on write, and search works out of
        the box — the certification boot's failure mode (datahelix#45,
        'relation "fts_sample_notes" does not exist')."""
        created = fts_client.put(
            "Sample",
            {"id": str(uuid.uuid4()), "name": "n2", "notes": "korokke recipe"},
        )
        results = fts_client.search("Sample", "korokke")
        assert [r["id"] for r in results] == [created["id"]]

    def test_put_syncs_content_when_fts_table_exists(self, fts_client):
        meta = fts_client._fts_table_metadata["Sample"][0]
        adapter = fts_client._storage
        with adapter._transaction() as conn:
            adapter._get_fts_store(conn).create_fts_table(
                meta.table_name, meta.get_fts_columns()
            )
        created = fts_client.put(
            "Sample",
            {"id": str(uuid.uuid4()), "name": "n2", "notes": "korokke recipe"},
        )
        with adapter._transaction() as conn:
            cur = conn.cursor()
            cur.execute(
                f"SELECT content FROM {meta.table_name} WHERE entity_id = %s",
                (created["id"],),
            )
            row = cur.fetchone()
        assert row is not None and "korokke" in row["content"]
