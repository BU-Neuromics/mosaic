"""Polymorphic tree-root ingest — designates_type dispatch (issue #80).

A schema that models polymorphism the standard LinkML way — an abstract (or
concrete) base with a ``designates_type`` discriminator and concrete
subclasses — must ingest its inlined collections under the base accessor,
with each instance routed to its concrete subclass by the discriminator:

- the abstract base gets a tree-root accessor (it was previously skipped, so
  the bundle hard-failed validation — consequence (a) of #80);
- an instance under a base accessor is stored as its concrete subclass, so
  subclass-specific fields persist and it is queryable as its real type
  (previously silently downcast to the base — consequence (b)).
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

import hippo
from hippo.cli.commands.ingest import IngestError, ingest_linkml_yaml


_SCHEMA = """\
id: https://example.org/poly
name: poly
prefixes:
  linkml: https://w3id.org/linkml/
imports:
  - linkml:types
  - hippo_core
default_range: string
classes:
  Donor:
    is_a: Entity
    attributes:
      donor_id:
        range: string
  Sample:                       # abstract polymorphic base
    is_a: Entity
    abstract: true
    attributes:
      category:
        range: string
        designates_type: true
  SolidSample:
    is_a: Sample
    attributes:
      tissue:
        range: string
  LiquidSample:
    is_a: Sample
    attributes:
      volume_ml:
        range: string
  Assay:                        # concrete polymorphic base
    is_a: Entity
    attributes:
      category:
        range: string
        designates_type: true
  RNASeqAssay:
    is_a: Assay
    attributes:
      platform:
        range: string
      read_length:
        range: integer
"""


@pytest.fixture
def registry(tmp_path: Path):
    schema = tmp_path / "schema.yaml"
    schema.write_text(_SCHEMA)
    return hippo.registry_for_schema(schema)


@pytest.fixture
def client(tmp_path: Path):
    schema = tmp_path / "schema.yaml"
    schema.write_text(_SCHEMA)
    return hippo.client_for_schema(schema, database_url=str(tmp_path / "h.db"))


def _bundle(tmp_path: Path, data: dict, name: str = "bundle.yaml") -> Path:
    p = tmp_path / name
    p.write_text(yaml.safe_dump(data))
    return p


class TestTreeRootAccessors:
    def test_abstract_polymorphic_base_gets_accessor(self, registry):
        names = {s.name for s in registry.tree_root_slots()}
        # Abstract base `Sample` declares a designates_type slot → accessor.
        assert "samples" in names
        # Concrete subclasses still get their own accessors.
        assert {"solid_samples", "liquid_samples"} <= names

    def test_plain_abstract_root_excluded(self, registry):
        names = {s.name for s in registry.tree_root_slots()}
        # `Entity` (abstract, no designator) must NOT get an accessor.
        assert "entities" not in names and "entitys" not in names


class TestPolymorphicDispatch:
    def test_abstract_base_collection_ingests_and_dispatches(
        self, tmp_path, client, registry
    ):
        bundle = _bundle(
            tmp_path,
            {
                "samples": [
                    {
                        "id": "S1",
                        "category": "SolidSample",
                        "tissue": "brain",
                        "is_available": True,
                    },
                    {
                        "id": "S2",
                        "category": "LiquidSample",
                        "volume_ml": "5",
                        "is_available": True,
                    },
                ]
            },
        )

        result = ingest_linkml_yaml(bundle, client, registry)
        assert result.errors == 0 and result.created == 2

        assert [e["id"] for e in client.query("SolidSample").items] == ["S1"]
        assert [e["id"] for e in client.query("LiquidSample").items] == ["S2"]
        # Subclass-specific fields persisted.
        assert client.get("SolidSample", "S1")["data"]["tissue"] == "brain"
        assert client.get("LiquidSample", "S2")["data"]["volume_ml"] == "5"

    def test_concrete_base_accessor_no_longer_downcasts(
        self, tmp_path, client, registry
    ):
        # The issue's case (b): an RNASeqAssay under the base `assays:` key.
        bundle = _bundle(
            tmp_path,
            {
                "assays": [
                    {
                        "id": "A1",
                        "category": "RNASeqAssay",
                        "platform": "Illumina",
                        "read_length": 150,
                        "is_available": True,
                    }
                ]
            },
        )

        result = ingest_linkml_yaml(bundle, client, registry)
        assert result.errors == 0 and result.created == 1

        assert [e["id"] for e in client.query("RNASeqAssay").items] == ["A1"]
        got = client.get("RNASeqAssay", "A1")
        assert got["data"]["platform"] == "Illumina"
        assert got["data"]["read_length"] == 150

    def test_concrete_subclass_accessor_still_works(
        self, tmp_path, client, registry
    ):
        # The documented workaround (concrete accessor) must keep working.
        bundle = _bundle(
            tmp_path,
            {
                "solid_samples": [
                    {"id": "S9", "tissue": "liver", "is_available": True}
                ]
            },
        )
        result = ingest_linkml_yaml(bundle, client, registry)
        assert result.errors == 0 and result.created == 1
        assert client.get("SolidSample", "S9")["data"]["tissue"] == "liver"

    def test_unknown_discriminator_value_rejected(self, tmp_path, client, registry):
        # An out-of-family discriminator value is caught by up-front bundle
        # validation (the designator enum), so the whole ingest fails fast and
        # writes nothing — never reaching the per-instance dispatch guard.
        bundle = _bundle(
            tmp_path,
            {
                "samples": [
                    {"id": "S1", "category": "Nonexistent", "is_available": True}
                ]
            },
        )
        with pytest.raises(IngestError):
            ingest_linkml_yaml(bundle, client, registry)
        assert client.query("SolidSample").items == []

    def test_dispatch_guard_rejects_unknown_value_directly(self, registry):
        # The dispatch-level guard is the defense-in-depth fallback for when
        # validation is bypassed / schema drift: it refuses an unresolvable
        # discriminator value rather than mis-storing the instance.
        from hippo.cli.commands.ingest import _dispatch_class

        with pytest.raises(IngestError, match="does not name"):
            _dispatch_class(registry, "Sample", {"id": "S1", "category": "Nope"})

    def test_abstract_base_without_designator_value_errors(
        self, tmp_path, client, registry
    ):
        # Validation may pass an instance missing the (optional) designator;
        # dispatch must refuse to instantiate the abstract base.
        bundle = _bundle(
            tmp_path,
            {"samples": [{"id": "S1", "is_available": True}]},
        )
        result = ingest_linkml_yaml(bundle, client, registry)
        assert result.errors == 1
        assert "abstract" in result.error_messages[0].lower()
