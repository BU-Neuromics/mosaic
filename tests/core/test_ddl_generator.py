import pytest
from hippo.config.models import FieldDefinition, SchemaConfig
from hippo.core.storage.ddl_generator import DDLGenerator


class TestTypeMapping:
    def test_datetime_maps_to_text(self):
        gen = DDLGenerator()
        assert gen._map_type("datetime") == "TEXT"

    def test_boolean_maps_to_integer(self):
        gen = DDLGenerator()
        assert gen._map_type("boolean") == "INTEGER"

    def test_string_maps_to_text(self):
        gen = DDLGenerator()
        assert gen._map_type("string") == "TEXT"

    def test_integer_maps_to_integer(self):
        gen = DDLGenerator()
        assert gen._map_type("integer") == "INTEGER"

    def test_float_maps_to_real(self):
        gen = DDLGenerator()
        assert gen._map_type("float") == "REAL"

    def test_date_maps_to_text(self):
        gen = DDLGenerator()
        assert gen._map_type("date") == "TEXT"

    def test_list_maps_to_text(self):
        gen = DDLGenerator()
        assert gen._map_type("list") == "TEXT"

    def test_dict_maps_to_text(self):
        gen = DDLGenerator()
        assert gen._map_type("dict") == "TEXT"

    def test_uri_maps_to_text(self):
        gen = DDLGenerator()
        assert gen._map_type("uri") == "TEXT"

    def test_enum_maps_to_text(self):
        gen = DDLGenerator()
        assert gen._map_type("enum") == "TEXT"

    def test_unknown_type_defaults_to_text(self):
        gen = DDLGenerator()
        assert gen._map_type("unknown_type") == "TEXT"


class TestBasicTableGeneration:
    def test_single_entity_generates_table(self):
        schema = SchemaConfig(
            name="test_entity",
            version="1.0.0",
            fields=[
                FieldDefinition(name="name", type="string"),
            ],
        )
        gen = DDLGenerator()
        ddl = gen.generate([schema])
        assert len(ddl) >= 1
        assert 'CREATE TABLE "test_entity"' in ddl[0]

    def test_table_has_id_column(self):
        schema = SchemaConfig(
            name="test_entity",
            version="1.0.0",
            fields=[],
        )
        gen = DDLGenerator()
        ddl = gen.generate([schema])
        assert '"id" TEXT' in ddl[0]

    def test_table_has_is_available_column(self):
        schema = SchemaConfig(
            name="test_entity",
            version="1.0.0",
            fields=[],
        )
        gen = DDLGenerator()
        ddl = gen.generate([schema])
        assert '"is_available" INTEGER' in ddl[0]

    def test_is_available_has_default_1(self):
        schema = SchemaConfig(
            name="test_entity",
            version="1.0.0",
            fields=[],
        )
        gen = DDLGenerator()
        ddl = gen.generate([schema])
        assert "DEFAULT 1" in ddl[0]


class TestPrimaryKeyGeneration:
    def test_id_is_primary_key(self):
        schema = SchemaConfig(
            name="test_entity",
            version="1.0.0",
            fields=[],
        )
        gen = DDLGenerator()
        ddl = gen.generate([schema])
        assert "PRIMARY KEY" in ddl[0]

    def test_explicit_primary_key_field(self):
        schema = SchemaConfig(
            name="test_entity",
            version="1.0.0",
            fields=[
                FieldDefinition(name="uuid", type="string", primary_key=True),
            ],
        )
        gen = DDLGenerator()
        ddl = gen.generate([schema])
        assert "PRIMARY KEY" in ddl[0]


class TestForeignKeyGeneration:
    def test_field_references_foreign_key(self):
        schema = SchemaConfig(
            name="child_entity",
            version="1.0.0",
            fields=[
                FieldDefinition(
                    name="parent_id",
                    type="string",
                    references={"table": "parent_entity", "column": "id"},
                ),
            ],
        )
        gen = DDLGenerator()
        parent_schema = SchemaConfig(
            name="parent_entity",
            version="1.0.0",
            fields=[],
        )
        ddl = gen.generate([parent_schema, schema])
        fk_ddl = "\n".join(ddl)
        assert "FOREIGN KEY" in fk_ddl
        assert "parent_entity" in fk_ddl


class TestUniqueConstraintGeneration:
    def test_unique_field_generates_unique_constraint(self):
        schema = SchemaConfig(
            name="test_entity",
            version="1.0.0",
            fields=[
                FieldDefinition(name="email", type="string", unique=True),
            ],
        )
        gen = DDLGenerator()
        ddl = gen.generate([schema])
        assert "UNIQUE" in ddl[0]


class TestDefaultValueGeneration:
    def test_field_with_default(self):
        schema = SchemaConfig(
            name="test_entity",
            version="1.0.0",
            fields=[
                FieldDefinition(name="status", type="string", default="active"),
            ],
        )
        gen = DDLGenerator()
        ddl = gen.generate([schema])
        assert "DEFAULT 'active'" in ddl[0]

    def test_boolean_default(self):
        schema = SchemaConfig(
            name="test_entity",
            version="1.0.0",
            fields=[
                FieldDefinition(name="active", type="boolean", default=True),
            ],
        )
        gen = DDLGenerator()
        ddl = gen.generate([schema])
        assert "DEFAULT 1" in ddl[0]


class TestIndexGeneration:
    def test_indexed_field_generates_index(self):
        schema = SchemaConfig(
            name="test_entity",
            version="1.0.0",
            fields=[
                FieldDefinition(name="name", type="string", index=True),
            ],
        )
        gen = DDLGenerator()
        ddl = gen.generate([schema])
        assert len(ddl) == 2
        assert "CREATE INDEX" in ddl[1]

    def test_partial_index_with_index_partial(self):
        schema = SchemaConfig(
            name="test_entity",
            version="1.0.0",
            fields=[
                FieldDefinition(
                    name="name", type="string", index=True, index_partial=True
                ),
            ],
        )
        gen = DDLGenerator()
        ddl = gen.generate([schema])
        assert "WHERE is_available = 1" in ddl[1]


class TestClassTableInheritance:
    def test_child_table_with_base_has_foreign_key(self):
        parent_schema = SchemaConfig(
            name="parent_entity",
            version="1.0.0",
            fields=[
                FieldDefinition(name="created_at", type="datetime"),
            ],
        )
        child_schema = SchemaConfig(
            name="child_entity",
            version="1.0.0",
            base="parent_entity",
            fields=[
                FieldDefinition(name="name", type="string"),
            ],
        )
        gen = DDLGenerator()
        ddl = gen.generate([parent_schema, child_schema])
        fk_ddl = "\n".join(ddl)
        assert "FOREIGN KEY" in fk_ddl
        assert "parent_entity" in fk_ddl


class TestDependencyOrdering:
    def test_child_generated_after_parent(self):
        parent_schema = SchemaConfig(
            name="parent_entity",
            version="1.0.0",
            fields=[],
        )
        child_schema = SchemaConfig(
            name="child_entity",
            version="1.0.0",
            base="parent_entity",
            fields=[],
        )
        gen = DDLGenerator()
        ddl = gen.generate([child_schema, parent_schema])
        parent_idx = next(i for i, d in enumerate(ddl) if "parent_entity" in d)
        child_idx = next(i for i, d in enumerate(ddl) if "child_entity" in d)
        assert parent_idx < child_idx


class TestMultiEntitySchema:
    def test_multiple_entities_generated(self):
        schemas = [
            SchemaConfig(
                name="entity_a",
                version="1.0.0",
                fields=[FieldDefinition(name="field1", type="string")],
            ),
            SchemaConfig(
                name="entity_b",
                version="1.0.0",
                fields=[FieldDefinition(name="field2", type="string")],
            ),
        ]
        gen = DDLGenerator()
        ddl = gen.generate(schemas)
        assert len(ddl) == 2

    def test_complex_schema_with_all_features(self):
        schemas = [
            SchemaConfig(
                name="organization",
                version="1.0.0",
                fields=[
                    FieldDefinition(name="name", type="string", required=True),
                    FieldDefinition(
                        name="code", type="string", unique=True, index=True
                    ),
                    FieldDefinition(name="active", type="boolean", default=True),
                ],
                unique_constraints=[["name", "code"]],
                indexes=[
                    {"name": "idx_org_active", "columns": ["active"], "partial": True}
                ],
            ),
            SchemaConfig(
                name="user",
                version="1.0.0",
                fields=[
                    FieldDefinition(name="username", type="string", required=True),
                    FieldDefinition(
                        name="org_id",
                        type="string",
                        references={"table": "organization", "column": "id"},
                    ),
                    FieldDefinition(name="created_at", type="datetime"),
                ],
            ),
        ]
        gen = DDLGenerator()
        ddl = gen.generate(schemas)
        assert len(ddl) == 4
        full_ddl = "\n".join(ddl)
        assert "UNIQUE" in full_ddl
        assert "CREATE INDEX" in full_ddl
        assert "FOREIGN KEY" in full_ddl
