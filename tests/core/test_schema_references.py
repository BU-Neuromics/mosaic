"""Unit tests for HippoClient.schema_references()."""

import pytest

from hippo.core.client import HippoClient
from tests.support.linkml_schemas import build_registry


def client_with(classes):
    return HippoClient(registry=build_registry(classes)) if classes else HippoClient()


class TestSchemaReferencesNoSchemas:
    def test_returns_empty_when_no_schemas(self):
        assert HippoClient().schema_references("Donor") == []

    def test_returns_empty_when_schemas_is_none(self):
        assert HippoClient(registry=None).schema_references("Sample") == []


class TestSchemaReferencesEntityTypeNotFound:
    def test_returns_empty_for_unknown_entity_type(self):
        client = client_with({"Donor": {"attributes": {"id": {"identifier": True}}}})
        assert client.schema_references("Sample") == []


class TestSchemaReferencesNoReferences:
    def test_returns_empty_when_no_attributes_reference_classes(self):
        client = client_with(
            {
                "Donor": {
                    "attributes": {
                        "id": {"identifier": True},
                        "name": {"range": "string"},
                        "age": {"range": "integer"},
                    }
                }
            }
        )
        assert client.schema_references("Donor") == []

    def test_returns_empty_for_attributes_only_id(self):
        client = client_with({"Donor": {"attributes": {"id": {"identifier": True}}}})
        assert client.schema_references("Donor") == []


class TestSchemaReferencesSingleReference:
    def test_single_reference_slot(self):
        client = client_with(
            {
                "Donor": {"attributes": {"id": {"identifier": True}}},
                "Sample": {
                    "attributes": {
                        "id": {"identifier": True},
                        "donor_id": {"range": "Donor"},
                    }
                },
            }
        )
        assert client.schema_references("Sample") == [
            {"field": "donor_id", "target_entity_type": "Donor"}
        ]


class TestSchemaReferencesMultipleReferences:
    def test_multiple_reference_slots(self):
        client = client_with(
            {
                "Donor": {"attributes": {"id": {"identifier": True}}},
                "Tissue": {"attributes": {"id": {"identifier": True}}},
                "Sample": {
                    "attributes": {
                        "id": {"identifier": True},
                        "name": {"range": "string"},
                        "donor_id": {"range": "Donor"},
                        "tissue_id": {"range": "Tissue"},
                    }
                },
            }
        )
        refs = client.schema_references("Sample")
        assert len(refs) == 2
        assert {"field": "donor_id", "target_entity_type": "Donor"} in refs
        assert {"field": "tissue_id", "target_entity_type": "Tissue"} in refs

    def test_mixed_slots_only_references_returned(self):
        client = client_with(
            {
                "Sample": {"attributes": {"id": {"identifier": True}}},
                "Donor": {"attributes": {"id": {"identifier": True}}},
                "Datafile": {
                    "attributes": {
                        "id": {"identifier": True},
                        "uri": {"range": "uri"},
                        "checksum": {"range": "string"},
                        "sample_id": {"range": "Sample"},
                        "donor_id": {"range": "Donor"},
                        "size": {"range": "integer"},
                    }
                },
            }
        )
        refs = client.schema_references("Datafile")
        fields = {r["field"] for r in refs}
        assert fields == {"sample_id", "donor_id"}

    def test_unqueried_type_returns_empty(self):
        client = client_with(
            {
                "Donor": {
                    "attributes": {
                        "id": {"identifier": True},
                        "name": {"range": "string"},
                    }
                },
                "Sample": {
                    "attributes": {
                        "id": {"identifier": True},
                        "donor_id": {"range": "Donor"},
                    }
                },
            }
        )
        assert client.schema_references("Donor") == []
        assert client.schema_references("Sample") == [
            {"field": "donor_id", "target_entity_type": "Donor"}
        ]
