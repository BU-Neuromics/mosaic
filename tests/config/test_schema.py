import pytest
import tempfile
from pathlib import Path

from hippo.config import (
    SchemaConfig,
    FieldDefinition,
    SchemaError,
    load_schema,
)


class TestSchemaConfigModel:
    def test_valid_schema_config(self):
        schema = SchemaConfig(
            name="test_schema",
            version="1.0.0",
            description="Test schema",
            fields=[
                FieldDefinition(name="id", type="string", required=True),
                FieldDefinition(name="name", type="string"),
            ],
        )
        assert schema.name == "test_schema"
        assert schema.version == "1.0.0"
        assert len(schema.fields) == 2

    def test_schema_with_empty_name_raises(self):
        with pytest.raises(Exception):
            SchemaConfig(name="", version="1.0.0")

    def test_schema_with_empty_version_raises(self):
        with pytest.raises(Exception):
            SchemaConfig(name="test", version="")

    def test_invalid_field_type_raises(self):
        with pytest.raises(Exception):
            FieldDefinition(name="field1", type="invalid_type")

    def test_valid_field_types(self):
        valid_types = [
            "string",
            "integer",
            "float",
            "boolean",
            "date",
            "datetime",
            "list",
            "dict",
            "uri",
            "enum",
        ]
        for t in valid_types:
            field = FieldDefinition(name="test", type=t)
            assert field.type == t

    def test_schema_serialization(self):
        schema = SchemaConfig(
            name="test_schema",
            version="1.0.0",
            fields=[FieldDefinition(name="id", type="string", required=True)],
        )
        d = schema.to_dict()
        assert d["name"] == "test_schema"
        assert d["version"] == "1.0.0"

    def test_schema_deserialization(self):
        data = {
            "name": "test_schema",
            "version": "1.0.0",
            "fields": [{"name": "id", "type": "string", "required": True}],
        }
        schema = SchemaConfig.from_dict(data)
        assert schema.name == "test_schema"
        assert len(schema.fields) == 1

    def test_get_bases_single(self):
        schema = SchemaConfig(name="child", version="1.0", base="parent")
        assert schema.get_bases() == ["parent"]

    def test_get_bases_list(self):
        schema = SchemaConfig(name="child", version="1.0", base=["parent1", "parent2"])
        assert schema.get_bases() == ["parent1", "parent2"]

    def test_get_bases_none(self):
        schema = SchemaConfig(name="standalone", version="1.0")
        assert schema.get_bases() == []


class TestSchemaYAMLParsing:
    def test_valid_yaml_parsing(self, tmp_path):
        schema_file = tmp_path / "schema.yaml"
        schema_file.write_text("""
name: test_schema
version: 1.0.0
description: Test schema
fields:
  - name: id
    type: string
    required: true
  - name: name
    type: string
""")
        schema = load_schema(schema_file)
        assert schema.name == "test_schema"
        assert schema.version == "1.0.0"

    def test_invalid_yaml_syntax_raises(self, tmp_path):
        schema_file = tmp_path / "schema.yaml"
        schema_file.write_text("""
name: test
version: 1.0
invalid: yaml: content: [}
""")
        with pytest.raises(SchemaError) as exc_info:
            load_schema(schema_file)
        assert exc_info.value.error_code == "YAML_SYNTAX_ERROR"

    def test_missing_required_field_raises(self):
        with pytest.raises(SchemaError) as exc_info:
            load_schema({"version": "1.0.0"})
        assert exc_info.value.error_code == "VALIDATION_ERROR"


class TestInheritance:
    def test_single_base_inheritance(self, tmp_path):
        base_file = tmp_path / "base.yaml"
        base_file.write_text("""
name: base_schema
version: 1.0.0
fields:
  - name: id
    type: string
    required: true
""")
        child_file = tmp_path / "child.yaml"
        child_file.write_text("""
name: child_schema
version: 1.0.0
base: base_schema
fields:
  - name: name
    type: string
""")
        child_schema = load_schema(child_file)
        assert len(child_schema.fields) == 2
        field_names = [f.name for f in child_schema.fields]
        assert "id" in field_names
        assert "name" in field_names

    def test_multi_level_inheritance(self, tmp_path):
        grandparent_file = tmp_path / "grandparent.yaml"
        grandparent_file.write_text("""
name: grandparent
version: 1.0.0
fields:
  - name: created_at
    type: datetime
""")
        parent_file = tmp_path / "parent.yaml"
        parent_file.write_text("""
name: parent
version: 1.0.0
base: grandparent
fields:
  - name: id
    type: string
""")
        child_file = tmp_path / "child.yaml"
        child_file.write_text("""
name: child
version: 1.0.0
base: parent
fields:
  - name: name
    type: string
""")
        child_schema = load_schema(child_file)
        assert len(child_schema.fields) == 3

    def test_field_override_in_inheritance(self, tmp_path):
        base_file = tmp_path / "base.yaml"
        base_file.write_text("""
name: base_schema
version: 1.0.0
fields:
  - name: id
    type: string
""")
        child_file = tmp_path / "child.yaml"
        child_file.write_text("""
name: child_schema
version: 1.0.0
base: base_schema
fields:
  - name: id
    type: integer
""")
        child_schema = load_schema(child_file)
        assert len(child_schema.fields) == 1
        assert child_schema.fields[0].type == "integer"


class TestCycleDetection:
    def test_self_reference_cycle_raises(self, tmp_path):
        schema_file = tmp_path / "schema.yaml"
        schema_file.write_text("""
name: circular
version: 1.0.0
base: circular
fields:
  - name: id
    type: string
""")
        with pytest.raises(SchemaError) as exc_info:
            load_schema(schema_file)
        assert exc_info.value.error_code in ["CYCLE_DETECTED", "CIRCULAR_INHERITANCE"]

    def test_direct_cycle_raises(self, tmp_path):
        schema_a = tmp_path / "a.yaml"
        schema_a.write_text("""
name: schema_a
version: 1.0.0
base: schema_b
fields:
  - name: id
    type: string
""")
        schema_b = tmp_path / "b.yaml"
        schema_b.write_text("""
name: schema_b
version: 1.0.0
base: schema_a
fields:
  - name: id
    type: string
""")
        with pytest.raises(SchemaError) as exc_info:
            load_schema(tmp_path)
        assert exc_info.value.error_code in ["CYCLE_DETECTED", "CIRCULAR_INHERITANCE"]

    def test_three_schema_cycle_raises(self, tmp_path):
        schema_a = tmp_path / "a.yaml"
        schema_a.write_text("""
name: schema_a
version: 1.0.0
base: schema_c
fields:
  - name: id
    type: string
""")
        schema_b = tmp_path / "b.yaml"
        schema_b.write_text("""
name: schema_b
version: 1.0.0
base: schema_a
fields:
  - name: id
    type: string
""")
        schema_c = tmp_path / "c.yaml"
        schema_c.write_text("""
name: schema_c
version: 1.0.0
base: schema_b
fields:
  - name: id
    type: string
""")
        with pytest.raises(SchemaError) as exc_info:
            load_schema(tmp_path)
        assert exc_info.value.error_code in ["CYCLE_DETECTED", "CIRCULAR_INHERITANCE"]


class TestValidationErrors:
    def test_base_not_found_raises(self):
        with pytest.raises(SchemaError) as exc_info:
            load_schema(
                {
                    "name": "child",
                    "version": "1.0.0",
                    "base": "nonexistent_base",
                    "fields": [{"name": "id", "type": "string"}],
                }
            )
        assert exc_info.value.error_code == "BASE_NOT_FOUND"

    def test_duplicate_field_raises(self):
        with pytest.raises(SchemaError) as exc_info:
            load_schema(
                {
                    "name": "test",
                    "version": "1.0.0",
                    "fields": [
                        {"name": "id", "type": "string"},
                        {"name": "id", "type": "integer"},
                    ],
                }
            )
        assert exc_info.value.error_code == "DUPLICATE_FIELD"

    def test_invalid_field_type_raises(self):
        with pytest.raises(SchemaError) as exc_info:
            load_schema(
                {
                    "name": "test",
                    "version": "1.0.0",
                    "fields": [{"name": "field1", "type": "invalid_type"}],
                }
            )
        assert exc_info.value.error_code == "VALIDATION_ERROR"

    def test_missing_required_name_raises(self):
        with pytest.raises(SchemaError):
            load_schema(
                {
                    "name": "",
                    "version": "1.0.0",
                }
            )

    def test_missing_required_version_raises(self):
        with pytest.raises(SchemaError):
            load_schema(
                {
                    "name": "test",
                    "version": "",
                }
            )


class TestCyclePathReporting:
    def test_cycle_path_reported_in_error(self, tmp_path):
        schema_a = tmp_path / "a.yaml"
        schema_a.write_text("""
name: schema_a
version: 1.0.0
base: schema_b
fields:
  - name: id
    type: string
""")
        schema_b = tmp_path / "b.yaml"
        schema_b.write_text("""
name: schema_b
version: 1.0.0
base: schema_a
fields:
  - name: id
    type: string
""")
        try:
            load_schema(tmp_path)
        except SchemaError as e:
            assert len(e.cycle_path) > 0


class TestDeepInheritance:
    def test_deep_inheritance_chain(self, tmp_path):
        schemas = []
        for i in range(5):
            schema_file = tmp_path / f"level{i}.yaml"
            base = f"level{i - 1}" if i > 0 else None
            content = f"""
name: level{i}
version: 1.0.0
{f"base: {base}" if base else ""}
fields:
  - name: field{i}
    type: string
"""
            schema_file.write_text(content)
            schemas.append(schema_file)

        schema = load_schema(tmp_path / "level4.yaml")
        assert len(schema.fields) == 5
