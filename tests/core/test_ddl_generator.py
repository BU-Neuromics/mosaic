"""Tests for DDL generation from a LinkML-backed SchemaRegistry."""

import pytest

from hippo.core.storage.ddl_generator import DDLGenerator
from tests.support.linkml_schemas import build_registry


class TestTypeMapping:
    @pytest.mark.parametrize(
        "linkml_type,expected",
        [
            ("string", "TEXT"),
            ("integer", "INTEGER"),
            ("float", "REAL"),
            ("double", "REAL"),
            ("decimal", "REAL"),
            ("boolean", "INTEGER"),
            ("date", "TEXT"),
            ("datetime", "TEXT"),
            ("uri", "TEXT"),
            ("uriorcurie", "TEXT"),
        ],
    )
    def test_linkml_type_maps_to_sqlite(self, linkml_type: str, expected: str):
        assert DDLGenerator.TYPE_MAPPING[linkml_type] == expected

    def test_unknown_slot_range_defaults_to_text(self):
        reg = build_registry(
            {
                "item": {
                    "attributes": {
                        "id": {"identifier": True},
                        "mystery": {"range": "not-a-real-type"},
                    }
                }
            }
        )
        ddl = DDLGenerator().generate(reg)
        assert '"mystery" TEXT' in ddl[0]


class TestBasicTableGeneration:
    def test_emits_create_table(self):
        reg = build_registry(
            {
                "test_entity": {
                    "attributes": {
                        "id": {"identifier": True},
                        "name": {"range": "string"},
                    }
                }
            }
        )
        ddl = DDLGenerator().generate(reg)
        assert any('CREATE TABLE "test_entity"' in s for s in ddl)

    def test_includes_id_column(self):
        reg = build_registry(
            {"test_entity": {"attributes": {"id": {"identifier": True}}}}
        )
        ddl = DDLGenerator().generate(reg)
        assert '"id" TEXT' in ddl[0]

    def test_includes_is_available_with_default_1(self):
        reg = build_registry(
            {"test_entity": {"attributes": {"id": {"identifier": True}}}}
        )
        ddl = DDLGenerator().generate(reg)
        assert '"is_available" INTEGER' in ddl[0]
        assert "DEFAULT 1" in ddl[0]

    def test_includes_superseded_by_column(self):
        reg = build_registry(
            {"test_entity": {"attributes": {"id": {"identifier": True}}}}
        )
        ddl = DDLGenerator().generate(reg)
        assert '"superseded_by" TEXT' in ddl[0]

    def test_abstract_class_is_skipped(self):
        reg = build_registry(
            {
                "AbstractBase": {
                    "abstract": True,
                    "attributes": {"id": {"identifier": True}},
                },
                "Concrete": {
                    "is_a": "AbstractBase",
                    "attributes": {"name": {"range": "string"}},
                },
            }
        )
        ddl = DDLGenerator().generate(reg)
        assert not any('CREATE TABLE "AbstractBase"' in s for s in ddl)
        assert any('CREATE TABLE "Concrete"' in s for s in ddl)


class TestPrimaryKey:
    def test_identifier_slot_is_primary_key(self):
        reg = build_registry(
            {"test_entity": {"attributes": {"id": {"identifier": True}}}}
        )
        ddl = DDLGenerator().generate(reg)
        assert "PRIMARY KEY" in ddl[0]


class TestForeignKey:
    def test_class_range_becomes_foreign_key(self):
        reg = build_registry(
            {
                "parent_entity": {"attributes": {"id": {"identifier": True}}},
                "child_entity": {
                    "attributes": {
                        "id": {"identifier": True},
                        "parent_id": {"range": "parent_entity"},
                    }
                },
            }
        )
        ddl = "\n".join(DDLGenerator().generate(reg))
        assert "FOREIGN KEY" in ddl
        assert '"parent_entity"' in ddl


class TestUniqueConstraint:
    def test_hippo_unique_annotation_emits_unique(self):
        reg = build_registry(
            {
                "test_entity": {
                    "attributes": {
                        "id": {"identifier": True},
                        "email": {
                            "range": "string",
                            "annotations": {"hippo_unique": True},
                        },
                    }
                }
            }
        )
        ddl = DDLGenerator().generate(reg)
        assert "UNIQUE" in ddl[0]

    def test_linkml_unique_keys_emit_composite_unique(self):
        reg = build_registry(
            {
                "organization": {
                    "attributes": {
                        "id": {"identifier": True},
                        "name": {"range": "string"},
                        "code": {"range": "string"},
                    },
                    "unique_keys": {
                        "name_code": {"unique_key_slots": ["name", "code"]}
                    },
                }
            }
        )
        ddl = DDLGenerator().generate(reg)
        assert 'UNIQUE ("name", "code")' in ddl[0]


class TestDefaultValue:
    def test_string_default_via_ifabsent(self):
        reg = build_registry(
            {
                "test_entity": {
                    "attributes": {
                        "id": {"identifier": True},
                        "status": {
                            "range": "string",
                            "ifabsent": "active",
                        },
                    }
                }
            }
        )
        ddl = DDLGenerator().generate(reg)
        assert "DEFAULT 'active'" in ddl[0]


class TestIndexGeneration:
    def test_hippo_index_emits_create_index(self):
        reg = build_registry(
            {
                "test_entity": {
                    "attributes": {
                        "id": {"identifier": True},
                        "name": {
                            "range": "string",
                            "annotations": {"hippo_index": True},
                        },
                    }
                }
            }
        )
        ddl = DDLGenerator().generate(reg)
        assert len(ddl) == 2
        assert "CREATE INDEX" in ddl[1]
        assert "idx_test_entity_name" in ddl[1]

    def test_hippo_index_partial_adds_where(self):
        reg = build_registry(
            {
                "test_entity": {
                    "attributes": {
                        "id": {"identifier": True},
                        "name": {
                            "range": "string",
                            "annotations": {
                                "hippo_index": True,
                                "hippo_index_partial": True,
                            },
                        },
                    }
                }
            }
        )
        ddl = DDLGenerator().generate(reg)
        assert "WHERE is_available = 1" in ddl[1]


class TestInheritance:
    def test_child_class_has_foreign_key_to_parent(self):
        reg = build_registry(
            {
                "parent_entity": {
                    "attributes": {
                        "id": {"identifier": True},
                        "created_at": {"range": "datetime"},
                    }
                },
                "child_entity": {
                    "is_a": "parent_entity",
                    "attributes": {"name": {"range": "string"}},
                },
            }
        )
        ddl = "\n".join(DDLGenerator().generate(reg))
        assert "FOREIGN KEY" in ddl
        assert '"parent_entity"' in ddl

    def test_parent_table_generated_before_child(self):
        reg = build_registry(
            {
                "parent_entity": {"attributes": {"id": {"identifier": True}}},
                "child_entity": {
                    "is_a": "parent_entity",
                    "attributes": {},
                },
            }
        )
        ddl = DDLGenerator().generate(reg)
        parent_idx = next(i for i, s in enumerate(ddl) if "parent_entity" in s)
        child_idx = next(i for i, s in enumerate(ddl) if "child_entity" in s)
        assert parent_idx < child_idx


class TestMultiClass:
    def test_two_unrelated_classes_both_generated(self):
        reg = build_registry(
            {
                "entity_a": {
                    "attributes": {
                        "id": {"identifier": True},
                        "field1": {"range": "string"},
                    }
                },
                "entity_b": {
                    "attributes": {
                        "id": {"identifier": True},
                        "field2": {"range": "string"},
                    }
                },
            }
        )
        ddl = DDLGenerator().generate(reg)
        assert len(ddl) == 2

    def test_full_schema_with_unique_index_and_fk(self):
        reg = build_registry(
            {
                "organization": {
                    "attributes": {
                        "id": {"identifier": True},
                        "name": {"range": "string", "required": True},
                        "code": {
                            "range": "string",
                            "annotations": {
                                "hippo_unique": True,
                                "hippo_index": True,
                            },
                        },
                        "active": {
                            "range": "boolean",
                        },
                    }
                },
                "user": {
                    "attributes": {
                        "id": {"identifier": True},
                        "username": {"range": "string", "required": True},
                        "org_id": {"range": "organization"},
                        "created_at": {"range": "datetime"},
                    }
                },
            }
        )
        ddl = DDLGenerator().generate(reg)
        full = "\n".join(ddl)
        assert "UNIQUE" in full
        assert "CREATE INDEX" in full
        assert "FOREIGN KEY" in full
