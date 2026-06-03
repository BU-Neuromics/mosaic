"""Tests for ``DomainModule`` + single-hop ``evolve`` (PTS-338 / sec11 §11.2.4).

Covers the S2 acceptance criterion verbatim: *a v1→v2 domain migration
runs with full provenance and passes the gate.* The migration model is
read-old → write-new → supersede-old, fronted by a staged dry-run
validation gate that must block every committed write when the transform
output does not validate against the merged schema.
"""

import os
import tempfile

import pytest
import yaml
from linkml_runtime.utils.schemaview import SchemaView

from hippo.core.client import HippoClient
from hippo.core.exceptions import (
    EntityNotFoundError,
    MigrationGateError,
    MigrationStepNotFoundError,
)
from hippo.core.loaders.domain_module import (
    DomainModule,
    MigrationContext,
    MigrationStep,
)
from hippo.core.loaders.reference import LoadResult, ReferenceLoader
from hippo.core.loaders.schema_package import MigratableData, SchemaPackage
from hippo.core.storage.adapters.sqlite_adapter import SQLiteAdapter
from hippo.linkml_bridge import SchemaRegistry, _bundled_importmap


# ---------------------------------------------------------------------------
# Fixtures: a tiny user-domain schema with a `Widget` class. All domain
# slots are optional so v1-shape records (missing v2 slots) seed cleanly;
# the gate's teeth are exercised via type / unknown-slot violations.
# ---------------------------------------------------------------------------


def _build_widget_registry() -> SchemaRegistry:
    overlay = {
        "id": "https://example.org/hippo/test_domain_module",
        "name": "test_domain_module",
        "prefixes": {
            "linkml": "https://w3id.org/linkml/",
            "hippo": "https://w3id.org/hippo/",
        },
        "imports": ["linkml:types", "hippo_core"],
        "default_range": "string",
        "classes": {
            "Widget": {
                "is_a": "Entity",
                "attributes": {
                    "label": {"range": "string"},
                    "kind": {"range": "string"},
                    "count": {"range": "integer"},
                },
            }
        },
    }
    return SchemaRegistry(
        SchemaView(yaml.safe_dump(overlay), importmap=_bundled_importmap())
    )


class _WidgetModule(DomainModule):
    """Test DomainModule whose single v1→v2 step is injected at construction."""

    name = "widget"
    description = "Test first-party domain module (PTS-338)"

    def __init__(self, transform, *, duplicate: bool = False) -> None:
        self._transform = transform
        self._duplicate = duplicate

    def versions(self) -> list[str]:
        return ["v1", "v2", "test"]

    def schema_fragment(self) -> dict:
        # Not merged in these tests (the client's registry is built
        # directly); a minimal fragment satisfies the genus contract.
        return {"default_prefix": "widget", "classes": {}}

    def populates_types(self) -> list[str]:
        return ["Widget"]

    def migration_steps(self) -> list[MigrationStep]:
        step = MigrationStep(
            from_version="v1",
            to_version="v2",
            transform=self._transform,
            description="seed kind from label",
        )
        if self._duplicate:
            return [step, step]
        return [step]


def _v1_to_v2_set_kind(ctx: MigrationContext) -> None:
    """Happy transform: each v1 Widget becomes a new v2 Widget with `kind`."""
    for old in ctx.client.query("Widget").items:
        data = old["data"]
        ctx.plan.migrate(
            "Widget",
            old["id"],
            {"label": data.get("label"), "kind": "migrated"},
        )


def _v1_to_v2_bad_type(ctx: MigrationContext) -> None:
    """Invalid transform: stages a record with a non-integer `count`."""
    for old in ctx.client.query("Widget").items:
        ctx.plan.migrate(
            "Widget",
            old["id"],
            {"label": old["data"].get("label"), "count": "not-an-integer"},
        )


def _v1_to_v2_unknown_class(ctx: MigrationContext) -> None:
    """Invalid transform: stages a record for a class absent from the schema."""
    for old in ctx.client.query("Widget").items:
        ctx.plan.migrate("Gadget", old["id"], {"label": "x"})


@pytest.fixture
def db_path():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield os.path.join(tmpdir, "test_domain_module.db")


@pytest.fixture
def registry() -> SchemaRegistry:
    return _build_widget_registry()


@pytest.fixture
def client(db_path: str, registry: SchemaRegistry) -> HippoClient:
    storage = SQLiteAdapter(db_path, schema_registry=registry)
    return HippoClient(storage=storage, registry=registry)


def _seed_v1(client: HippoClient, n: int) -> list[str]:
    """Seed `n` v1-shape Widget records (label only); return their ids."""
    ids = []
    for i in range(n):
        wid = f"w{i}"
        client.put(
            "Widget",
            {"id": wid, "label": f"label-{i}", "is_available": True},
            bypass_validation=True,
        )
        ids.append(wid)
    return ids


# ---------------------------------------------------------------------------
# Genus / species contract
# ---------------------------------------------------------------------------


class TestContract:
    def test_is_schema_package_subclass(self) -> None:
        assert issubclass(DomainModule, SchemaPackage)

    def test_instance_satisfies_migratable_data_protocol(self) -> None:
        module = _WidgetModule(_v1_to_v2_set_kind)
        assert isinstance(module, MigratableData)

    def test_reference_loader_does_not_satisfy_migratable_data(self) -> None:
        """The protocol keys on ``migration_steps`` — only the migration
        species matches it, so the orchestrator can dispatch by isinstance."""

        class _Ref(ReferenceLoader):
            name = "ref"
            description = "x"

            def versions(self) -> list[str]:
                return ["1"]

            def schema_fragment(self) -> dict:
                return {"default_prefix": "ref"}

            def load(self, client, version, params=None) -> LoadResult:
                return LoadResult()

        assert not isinstance(_Ref(), MigratableData)

    def test_provision_is_genus_noop(self, client: HippoClient) -> None:
        module = _WidgetModule(_v1_to_v2_set_kind)
        assert module.provision(client, "v2") is None

    def test_deprovision_is_genus_noop(self, client: HippoClient) -> None:
        # S2 leaves deprovision as the inherited genus no-op; refuse-by-
        # default + dependents guard are S3 (sec11 §11.4.3 / §11.7.2).
        module = _WidgetModule(_v1_to_v2_set_kind)
        assert module.deprovision(client, "v2") is None


# ---------------------------------------------------------------------------
# Single-hop evolve — happy path with full provenance
# ---------------------------------------------------------------------------


class TestSingleHopEvolve:
    def test_migrates_v1_to_v2_writing_new_superseding_old(
        self, client: HippoClient
    ) -> None:
        old_ids = _seed_v1(client, 3)
        module = _WidgetModule(_v1_to_v2_set_kind)

        result = module.evolve(client, "v1", "v2")

        assert isinstance(result, LoadResult)
        assert result.created == 3
        assert len(result.entities) == 3

        # New records exist in v2 shape (kind set, available).
        for ref in result.entities:
            assert ref.type == "Widget"
            new = client.get("Widget", ref.id)
            assert new["data"]["kind"] == "migrated"

        # Old records are superseded: unavailable + superseded_by set.
        for old_id in old_ids:
            with pytest.raises(EntityNotFoundError):
                client.get("Widget", old_id)
            superseded = client.get(
                "Widget", old_id, include_unavailable=True
            )
            assert superseded["superseded_by"] is not None

    def test_writes_supersede_provenance_tagged_as_migration(
        self, client: HippoClient
    ) -> None:
        _seed_v1(client, 1)
        module = _WidgetModule(_v1_to_v2_set_kind)

        module.evolve(client, "v1", "v2")

        history = client.history("w0")
        supersede_events = [
            e for e in history if e["operation_type"] == "supersede"
        ]
        assert len(supersede_events) == 1
        event = supersede_events[0]
        # actor = module name; reason names the hop ⇒ reads as a migration.
        assert event["user_id"] == "widget"
        assert event["state_snapshot"]["reason"] == "widget migration v1→v2"

    def test_new_record_has_create_event_and_superseded_by_edge(
        self, client: HippoClient
    ) -> None:
        _seed_v1(client, 1)
        module = _WidgetModule(_v1_to_v2_set_kind)

        result = module.evolve(client, "v1", "v2")
        new_id = result.entities[0].id

        new_history = client.history(new_id)
        assert any(e["operation_type"] == "create" for e in new_history)

        # superseded_by relationship edge old → new.
        storage = client._storage
        with storage._transaction() as conn:
            rel_store = storage._get_relationship_store(conn)
            rels = list(
                rel_store.find(
                    source_id="w0",
                    target_id=new_id,
                    relationship_type="superseded_by",
                )
            )
        assert len(rels) == 1

    def test_migrates_all_records_not_just_first_page(
        self, client: HippoClient
    ) -> None:
        # client.query applies no default page limit; guard that evolve
        # migrates the whole set, not page one (advisor caution).
        old_ids = _seed_v1(client, 25)
        module = _WidgetModule(_v1_to_v2_set_kind)

        result = module.evolve(client, "v1", "v2")

        assert result.created == 25
        for old_id in old_ids:
            superseded = client.get(
                "Widget", old_id, include_unavailable=True
            )
            assert superseded["superseded_by"] is not None


# ---------------------------------------------------------------------------
# Hard validation gate — must block committed writes on invalid output
# ---------------------------------------------------------------------------


class TestValidationGate:
    def test_gate_blocks_commit_and_leaves_db_untouched(
        self, client: HippoClient
    ) -> None:
        old_ids = _seed_v1(client, 2)
        module = _WidgetModule(_v1_to_v2_bad_type)

        with pytest.raises(MigrationGateError):
            module.evolve(client, "v1", "v2")

        # Nothing committed: old records still available, none superseded,
        # no supersede provenance events, and no new Widget rows.
        for old_id in old_ids:
            entity = client.get("Widget", old_id)
            assert entity["superseded_by"] is None
            history = client.history(old_id)
            assert not any(
                e["operation_type"] == "supersede" for e in history
            )
        assert len(client.query("Widget").items) == 2

    def test_gate_error_carries_validation_messages(
        self, client: HippoClient
    ) -> None:
        _seed_v1(client, 1)
        module = _WidgetModule(_v1_to_v2_bad_type)

        with pytest.raises(MigrationGateError) as exc_info:
            module.evolve(client, "v1", "v2")

        err = exc_info.value
        assert err.package == "widget"
        assert err.from_version == "v1"
        assert err.to_version == "v2"
        assert err.errors
        assert any("integer" in m for m in err.errors)

    def test_gate_blocks_record_for_undefined_class(
        self, client: HippoClient
    ) -> None:
        _seed_v1(client, 1)
        module = _WidgetModule(_v1_to_v2_unknown_class)

        with pytest.raises(MigrationGateError):
            module.evolve(client, "v1", "v2")

        assert client.get("Widget", "w0")["superseded_by"] is None

    def test_gate_blocks_missing_required_v2_field(self, db_path: str) -> None:
        # Canonical "v2 adds a required field" story: a transform that
        # stages a record omitting the now-required slot fails the gate
        # before any write. Staged via plan.put (no seeding) so the
        # required-field NOT NULL column is never inserted into.
        overlay = {
            "id": "https://example.org/hippo/test_required",
            "name": "test_required",
            "prefixes": {
                "linkml": "https://w3id.org/linkml/",
                "hippo": "https://w3id.org/hippo/",
            },
            "imports": ["linkml:types", "hippo_core"],
            "default_range": "string",
            "classes": {
                "Gizmo": {
                    "is_a": "Entity",
                    "attributes": {
                        "label": {"range": "string"},
                        "kind": {"range": "string", "required": True},
                    },
                }
            },
        }
        reg = SchemaRegistry(
            SchemaView(yaml.safe_dump(overlay), importmap=_bundled_importmap())
        )
        client = HippoClient(
            storage=SQLiteAdapter(db_path, schema_registry=reg), registry=reg
        )

        def _stage_missing_required(ctx: MigrationContext) -> None:
            ctx.plan.put("Gizmo", {"label": "no kind here"})

        module = _WidgetModule(_stage_missing_required)
        with pytest.raises(MigrationGateError) as exc_info:
            module.evolve(client, "v1", "v2")
        assert any("kind" in m for m in exc_info.value.errors)
        # Nothing committed.
        assert len(client.query("Gizmo").items) == 0

    def test_gate_requires_a_schema_backed_client(self) -> None:
        # No registry ⇒ the gate cannot run; evolve refuses rather than
        # committing unvalidated writes.
        client = HippoClient()

        def _stage(ctx: MigrationContext) -> None:
            ctx.plan.put("Widget", {"label": "x"})

        module = _WidgetModule(_stage)
        with pytest.raises(MigrationGateError):
            module.evolve(client, "v1", "v2")


# ---------------------------------------------------------------------------
# Step resolution (single-hop; multi-hop is S3)
# ---------------------------------------------------------------------------


class TestStepResolution:
    def test_unknown_hop_fails_loud(self, client: HippoClient) -> None:
        module = _WidgetModule(_v1_to_v2_set_kind)
        with pytest.raises(MigrationStepNotFoundError) as exc_info:
            module.evolve(client, "v2", "v3")
        assert exc_info.value.available_steps == [("v1", "v2")]

    def test_duplicate_step_fails_loud(self, client: HippoClient) -> None:
        module = _WidgetModule(_v1_to_v2_set_kind, duplicate=True)
        with pytest.raises(MigrationStepNotFoundError):
            module.evolve(client, "v1", "v2")
