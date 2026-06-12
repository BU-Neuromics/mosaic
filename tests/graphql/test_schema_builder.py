"""Schema-generation tests: LinkML in, generated GraphQL SDL/types out.

No storage involved — these assert the shape of the strawberry schema
rendered from the shared type model (``hippo.core.schema_typing``) for
the fixture LinkML schema in ``conftest``.
"""

from __future__ import annotations

import re

import pytest

from hippo.core.schema_typing import build_type_model, exposed_class_names
from hippo.graphql import build_graphql_schema
from hippo.graphql.schema_builder import (
    INFRASTRUCTURE_CLASSES,
    GraphQLTypeBuilder,
    camel_case,
    snake_case,
)
from hippo.linkml_bridge import SchemaRegistry


@pytest.fixture(scope="module")
def sdl(registry: SchemaRegistry) -> str:
    return str(build_graphql_schema(registry))


def _block(sdl: str, header: str) -> str:
    """Extract one ``type X { ... }`` block from the SDL."""
    match = re.search(rf"^{re.escape(header)} \{{\n(.*?)^\}}", sdl, re.M | re.S)
    assert match is not None, f"{header} not found in SDL"
    return match.group(1)


class TestObjectTypeGeneration:
    def test_concrete_entity_classes_get_object_types(self, sdl):
        for name in ("Donor", "Sample", "Study"):
            assert f"type {name} " in sdl or f"type {name} {{" in sdl

    def test_infrastructure_classes_are_excluded(self, sdl):
        for name in INFRASTRUCTURE_CLASSES:
            assert f"type {name} {{" not in sdl

    def test_external_id_is_exposed_like_typed_client(self, sdl):
        # ExternalID is a concrete hippo_core class exposed by the
        # schema-typing core (issues #47/#48) — same class set as the
        # typed client; GraphQL mirrors that.
        assert "type ExternalID" in sdl

    def test_scalar_range_mappings(self, sdl):
        sample = _block(sdl, "type Sample")
        assert "name: String!" in sample  # required slot
        assert "volumeMl: Float" in sample
        assert "replicateCount: Int" in sample
        assert "isTumor: Boolean" in sample
        assert "collectedAt: DateTime" in sample

    def test_system_and_temporal_fields(self, sdl):
        sample = _block(sdl, "type Sample")
        assert "id: ID!" in sample
        assert "isAvailable: Boolean!" in sample
        for computed in (
            "version: Int",
            "createdAt: DateTime",
            "updatedAt: DateTime",
            "schemaVersion: String",
            "createdBy: String",
            "updatedBy: String",
            "supersededBy: ID",
        ):
            assert computed in sample, computed

    def test_enum_generation(self, sdl):
        enum_block = _block(sdl, "enum SexEnum")
        for member in ("male", "female", "unknown"):
            assert member in enum_block
        donor = _block(sdl, "type Donor")
        assert "sex: SexEnum" in donor


class TestRelationshipFields:
    def test_reference_slot_gets_raw_id_and_resolved_field(self, sdl):
        sample = _block(sdl, "type Sample")
        assert "donorId: ID" in sample  # raw stored UUID
        assert "donor: Donor" in sample  # graph traversal

    def test_self_reference_without_id_suffix(self, sdl):
        sample = _block(sdl, "type Sample")
        # Slot is named `parent` (no _id suffix): raw field derives the
        # _id name, resolved field keeps the natural name.
        assert "parentId: ID" in sample
        assert "parent: Sample" in sample

    def test_multivalued_reference(self, sdl):
        study = _block(sdl, "type Study")
        assert "sampleIds: [ID!]" in study
        assert "samples: [Sample!]!" in study


class TestPageTypes:
    def test_page_type_mirrors_paginated_result(self, sdl):
        page = _block(sdl, "type SamplePage")
        assert "items: [Sample!]!" in page
        assert "total: Int!" in page
        assert "limit: Int!" in page
        assert "offset: Int!" in page


class TestInputTypes:
    def test_create_input_keeps_required_slots_required(self, sdl):
        block = _block(sdl, "input SampleCreateInput")
        assert "name: String!" in block

    def test_update_input_is_fully_optional(self, sdl):
        block = _block(sdl, "input SampleUpdateInput")
        assert "name: String!" not in block
        assert "name: String" in block

    def test_id_is_never_required_on_inputs(self, sdl):
        block = _block(sdl, "input SampleCreateInput")
        assert "id: String!" not in block

    def test_reference_inputs_use_slot_names(self, sdl):
        # Inputs key on the LinkML slot name (donorId / parent), taking
        # the target UUID — the write payload maps 1:1 onto slot names.
        block = _block(sdl, "input SampleCreateInput")
        assert "donorId: ID" in block
        assert "parent: ID" in block


class TestRootTypes:
    def test_query_root_per_entity(self, sdl):
        query = _block(sdl, "type Query")
        assert "sample(id: ID!): Sample" in query
        assert "samples(" in query and "SamplePage!" in query
        assert "filterMode: FilterMode! = AND" in query
        assert "limit: Int! = 100" in query
        assert "offset: Int! = 0" in query
        assert "entityHistory(entityId: ID!): [ProvenanceEntry!]!" in query

    def test_search_query_per_entity(self, sdl):
        query = _block(sdl, "type Query")
        assert "searchSamples(q: String!" in query
        assert "searchDonors(q: String!" in query
        assert "[Sample!]!" in query

    def test_supersession_query(self, sdl):
        query = _block(sdl, "type Query")
        assert "supersededBy(id: ID!): SupersessionInfo!" in query
        info = _block(sdl, "type SupersessionInfo")
        assert "entityId: ID!" in info
        assert "supersededBy: ID" in info
        assert "chain: [ID!]!" in info

    def test_hippo_schema_introspection_queries(self, sdl):
        query = _block(sdl, "type Query")
        assert "hippoSchema: [HippoEntityTypeInfo!]!" in query
        assert "hippoEntityType(name: String!): HippoEntityTypeInfo" in query
        info = _block(sdl, "type HippoEntityTypeInfo")
        assert "fields: [HippoSlotInfo!]!" in info
        assert "relationships: [HippoReferenceInfo!]!" in info

    def test_mutation_root_per_entity(self, sdl):
        mutation = _block(sdl, "type Mutation")
        assert "createSample(data: SampleCreateInput!): Sample!" in mutation
        assert (
            "updateSample(id: ID!, data: SampleUpdateInput!): Sample!" in mutation
        )
        assert "setSampleAvailability(" in mutation
        assert "supersedeSample(" in mutation

    def test_bulk_availability_mutation_per_entity(self, sdl):
        mutation = _block(sdl, "type Mutation")
        assert (
            "setSampleAvailabilityBulk(ids: [ID!]!, isAvailable: Boolean!"
            in mutation
        )
        result = _block(sdl, "type BulkAvailabilityResult")
        assert "total: Int!" in result
        assert "succeeded: Int!" in result
        assert "failed: Int!" in result
        assert "failures: [BulkAvailabilityFailure!]!" in result

    def test_no_delete_mutations(self, sdl):
        # No hard deletes — availability transitions only (sec3).
        mutation = _block(sdl, "type Mutation")
        assert "deleteSample" not in mutation
        assert "deleteDonor" not in mutation


class TestTypingCoreAlignment:
    """The GraphQL surface renders the shared type model verbatim."""

    def test_entity_set_is_the_typing_core_class_set(self, registry):
        builder = GraphQLTypeBuilder(registry).build()
        assert sorted(builder.entities) == exposed_class_names(registry)

    def test_plural_names_come_from_the_shared_accessor(self, registry):
        builder = GraphQLTypeBuilder(registry).build()
        model = build_type_model(registry)
        for class_name, entity in builder.entities.items():
            assert entity.plural_name == model[class_name].accessor_name

    def test_slot_specs_mirror_the_model_slots(self, registry):
        builder = GraphQLTypeBuilder(registry).build()
        model = build_type_model(registry)
        for class_name, entity in builder.entities.items():
            assert [s.slot_name for s in entity.slots] == [
                f.name for f in model[class_name].fields
            ]
            assert [s.kind for s in entity.slots] == [
                f.kind.value for f in model[class_name].fields
            ]


class TestBuilder:
    def test_build_is_idempotent(self, registry):
        builder = GraphQLTypeBuilder(registry).build()
        first = dict(builder.entities)
        builder.build()
        assert builder.entities == first

    def test_empty_schema_raises(self):
        # hippo_core alone has exactly one concrete non-infrastructure
        # class (ExternalID); a registry can never really be empty, so
        # exercise the guard through a builder with no entities.
        from hippo.graphql.resolvers import build_graphql_schema as build_with_builder

        registry = SchemaRegistry.from_yaml(GRAPHQL_CORE_ONLY)
        builder = GraphQLTypeBuilder(registry)
        builder._built = True  # bypass generation: simulate no entities
        with pytest.raises(ValueError, match="no concrete entity classes"):
            build_with_builder(registry, builder=builder)


GRAPHQL_CORE_ONLY = """
id: https://example.org/hippo/test_graphql_core_only
name: test_graphql_core_only
prefixes:
  linkml: https://w3id.org/linkml/
imports:
  - linkml:types
  - hippo_core
default_range: string
"""


class TestNamingHelpers:
    def test_snake_case(self):
        assert snake_case("DNASample") == "dna_sample"
        assert snake_case("Sample") == "sample"
        assert snake_case("ExternalID") == "external_id"

    def test_camel_case(self):
        assert camel_case("create_sample") == "createSample"
        assert camel_case("samples") == "samples"
        assert camel_case("set_dna_sample_availability") == "setDnaSampleAvailability"
