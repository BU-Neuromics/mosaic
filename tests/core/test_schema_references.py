"""Unit tests for HippoClient.schema_references()."""

import pytest

from hippo.config.models import FieldDefinition, SchemaConfig
from hippo.core.client import HippoClient


def make_client(schemas=None):
    return HippoClient(schemas=schemas)


def make_schema(name, fields=None):
    return SchemaConfig(name=name, version="1.0", fields=fields or [])


def make_field(name, field_type="string", references=None):
    return FieldDefinition(name=name, type=field_type, references=references)


class TestSchemaReferencesNoSchemas:
    def test_returns_empty_when_no_schemas(self):
        client = make_client()
        assert client.schema_references("Donor") == []

    def test_returns_empty_when_schemas_is_none(self):
        client = make_client(schemas=None)
        assert client.schema_references("Sample") == []


class TestSchemaReferencesEntityTypeNotFound:
    def test_returns_empty_for_unknown_entity_type(self):
        schemas = {"Donor": make_schema("Donor")}
        client = make_client(schemas=schemas)
        assert client.schema_references("Sample") == []

    def test_returns_empty_for_empty_schemas_dict(self):
        client = make_client(schemas={})
        assert client.schema_references("Donor") == []


class TestSchemaReferencesNoReferences:
    def test_returns_empty_when_no_fields_have_references(self):
        schemas = {
            "Donor": make_schema(
                "Donor",
                fields=[
                    make_field("name"),
                    make_field("age", "integer"),
                ],
            )
        }
        client = make_client(schemas=schemas)
        assert client.schema_references("Donor") == []

    def test_returns_empty_for_empty_fields_list(self):
        schemas = {"Donor": make_schema("Donor")}
        client = make_client(schemas=schemas)
        assert client.schema_references("Donor") == []

    def test_ignores_references_dict_without_entity_type_key(self):
        schemas = {
            "Sample": make_schema(
                "Sample",
                fields=[
                    make_field("donor_id", references={"other_key": "Donor"}),
                ],
            )
        }
        client = make_client(schemas=schemas)
        assert client.schema_references("Sample") == []


class TestSchemaReferencesSingleReference:
    def test_single_reference_field(self):
        schemas = {
            "Sample": make_schema(
                "Sample",
                fields=[
                    make_field("donor_id", references={"entity_type": "Donor"}),
                ],
            )
        }
        client = make_client(schemas=schemas)
        refs = client.schema_references("Sample")
        assert refs == [{"field": "donor_id", "target_entity_type": "Donor"}]

    def test_namespaced_target_entity_type(self):
        schemas = {
            "Sample": make_schema(
                "Sample",
                fields=[
                    make_field("tissue_id", references={"entity_type": "tissue.Tissue"}),
                ],
            )
        }
        client = make_client(schemas=schemas)
        refs = client.schema_references("Sample")
        assert refs == [{"field": "tissue_id", "target_entity_type": "tissue.Tissue"}]


class TestSchemaReferencesMultipleReferences:
    def test_multiple_reference_fields(self):
        schemas = {
            "Sample": make_schema(
                "Sample",
                fields=[
                    make_field("name"),
                    make_field("donor_id", references={"entity_type": "Donor"}),
                    make_field("tissue_id", references={"entity_type": "Tissue"}),
                ],
            )
        }
        client = make_client(schemas=schemas)
        refs = client.schema_references("Sample")
        assert len(refs) == 2
        assert {"field": "donor_id", "target_entity_type": "Donor"} in refs
        assert {"field": "tissue_id", "target_entity_type": "Tissue"} in refs

    def test_mixed_fields_only_references_returned(self):
        schemas = {
            "Datafile": make_schema(
                "Datafile",
                fields=[
                    make_field("uri", "uri"),
                    make_field("checksum"),
                    make_field("sample_id", references={"entity_type": "Sample"}),
                    make_field("donor_id", references={"entity_type": "Donor"}),
                    make_field("size", "integer"),
                ],
            )
        }
        client = make_client(schemas=schemas)
        refs = client.schema_references("Datafile")
        assert len(refs) == 2
        fields = {r["field"] for r in refs}
        assert fields == {"sample_id", "donor_id"}

    def test_multiple_schemas_only_queried_type_returned(self):
        schemas = {
            "Donor": make_schema(
                "Donor",
                fields=[make_field("name")],
            ),
            "Sample": make_schema(
                "Sample",
                fields=[make_field("donor_id", references={"entity_type": "Donor"})],
            ),
        }
        client = make_client(schemas=schemas)
        assert client.schema_references("Donor") == []
        assert client.schema_references("Sample") == [
            {"field": "donor_id", "target_entity_type": "Donor"}
        ]
