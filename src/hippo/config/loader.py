from pathlib import Path
from typing import Union, Optional
from collections import defaultdict
from copy import deepcopy

import yaml
from pydantic import ValidationError as PydanticValidationError

from .core import (
    ConfigError,
    ValidationError as ValidationErrorBase,
    SchemaError,
    substitute_env_vars,
)
from .models import HippoConfig, SchemaConfig, FieldDefinition


def load_hippo_config(config_path: Union[str, Path]) -> HippoConfig:
    config_path = Path(config_path)

    if not config_path.exists():
        raise ConfigError(f"Configuration file not found: {config_path}")

    try:
        with open(config_path) as f:
            raw_config = yaml.safe_load(f) or {}
    except yaml.YAMLError as e:
        raise ConfigError(f"invalid YAML syntax: {e}")

    try:
        substituted_config = substitute_env_vars(raw_config)
    except ConfigError:
        raise

    try:
        return HippoConfig(**substituted_config)
    except PydanticValidationError as e:
        errors = e.errors()
        if errors:
            first_error = errors[0]
            loc = ".".join(str(l) for l in first_error["loc"])
            msg = first_error["msg"]
            input_val = first_error.get("input")
            type_info = first_error.get("type", "unknown")
            if type_info == "missing":
                raise ConfigError(
                    f"Missing required field: '{loc}'",
                    field_name=loc,
                )
            raise ValidationErrorBase(
                f"Configuration validation failed for field '{loc}': {msg} (expected {type_info}, got {input_val})",
                expected_type=type_info,
                actual_value=input_val,
            )
        raise ValidationErrorBase(
            "Configuration validation failed", expected_type=None, actual_value=None
        )


class SchemaParser:
    MAX_INHERITANCE_DEPTH = 20

    def __init__(self, schema_dir: Optional[Path] = None):
        self.schema_dir = schema_dir
        self._schema_cache: dict[str, dict] = {}
        self._resolved_schemas: dict[str, SchemaConfig] = {}

    def load(self, source: Union[str, Path, dict]) -> SchemaConfig:
        if isinstance(source, (str, Path)):
            path = Path(source)
            if not path.exists():
                raise SchemaError(
                    f"Schema file not found: {path}",
                    error_code="FILE_NOT_FOUND",
                )
            if path.is_dir():
                return self.load_schema_dir(path)
            return self.load_schema_file(path)
        elif isinstance(source, dict):
            return self.load_schema_dict(source)
        else:
            raise SchemaError(
                f"Invalid source type: {type(source)}",
                error_code="INVALID_SOURCE",
            )

    def load_schema_file(self, path: Path) -> SchemaConfig:
        try:
            with open(path) as f:
                raw_schema = yaml.safe_load(f) or {}
        except yaml.YAMLError as e:
            raise SchemaError(
                f"Invalid YAML syntax in schema file: {e}",
                error_code="YAML_SYNTAX_ERROR",
            )

        if self.schema_dir is None:
            self.schema_dir = path.parent

        for schema_file in self.schema_dir.glob("*.yaml"):
            try:
                with open(schema_file) as f:
                    raw = yaml.safe_load(f) or {}
                schema_name = raw.get("name")
                if schema_name and schema_name not in self._schema_cache:
                    self._schema_cache[schema_name] = raw
            except yaml.YAMLError:
                pass

        for schema_file in self.schema_dir.glob("*.yml"):
            try:
                with open(schema_file) as f:
                    raw = yaml.safe_load(f) or {}
                schema_name = raw.get("name")
                if schema_name and schema_name not in self._schema_cache:
                    self._schema_cache[schema_name] = raw
            except yaml.YAMLError:
                pass

        return self.load_schema_dict(raw_schema)

    def _load_base_schema(self, path: Path, loaded: set[str]) -> None:
        if path.stem in loaded:
            return
        loaded.add(path.stem)

        try:
            with open(path) as f:
                raw_schema = yaml.safe_load(f) or {}
        except yaml.YAMLError as e:
            raise SchemaError(
                f"Invalid YAML in {path}: {e}",
                error_code="YAML_SYNTAX_ERROR",
            )

        schema_name = raw_schema.get("name")
        if schema_name and schema_name not in self._schema_cache:
            self._schema_cache[schema_name] = raw_schema
            base = raw_schema.get("base")
            if base and self.schema_dir:
                bases = [base] if isinstance(base, str) else base
                for base_name in bases:
                    base_file = self.schema_dir / f"{base_name}.yaml"
                    if base_file.exists():
                        self._load_base_schema(base_file, loaded)

    def load_schema_dir(self, schema_dir: Path) -> SchemaConfig:
        self.schema_dir = schema_dir
        schema_files = list(schema_dir.glob("*.yaml")) + list(schema_dir.glob("*.yml"))

        if not schema_files:
            raise SchemaError(
                f"No schema files found in {schema_dir}",
                error_code="NO_SCHEMAS_FOUND",
            )

        for schema_file in schema_files:
            try:
                with open(schema_file) as f:
                    raw_schema = yaml.safe_load(f) or {}
            except yaml.YAMLError as e:
                raise SchemaError(
                    f"Invalid YAML in {schema_file}: {e}",
                    error_code="YAML_SYNTAX_ERROR",
                )

            schema_name = raw_schema.get("name")
            if schema_name:
                self._schema_cache[schema_name] = raw_schema

        return self._resolve_schemas()

    def load_schema_dict(self, raw_schema: dict) -> SchemaConfig:
        try:
            schema = SchemaConfig(**raw_schema)
        except PydanticValidationError as e:
            errors = e.errors()
            if errors:
                first_error = errors[0]
                loc = ".".join(str(l) for l in first_error["loc"])
                msg = first_error["msg"]
                raise SchemaError(
                    f"Schema validation failed for field '{loc}': {msg}",
                    error_code="VALIDATION_ERROR",
                    field_name=loc,
                )
            raise SchemaError(
                "Schema validation failed",
                error_code="VALIDATION_ERROR",
            )

        self._validate_schema(schema, raw_schema)

        schema_name = schema.name
        if schema_name not in self._schema_cache:
            self._schema_cache[schema_name] = raw_schema

        self._target_schema_name = schema_name
        return self._resolve_schemas()

    def _validate_schema(self, schema: SchemaConfig, raw_schema: dict) -> None:
        field_names = set()
        for field in schema.fields:
            if field.name in field_names:
                raise SchemaError(
                    f"Duplicate field name: '{field.name}'",
                    error_code="DUPLICATE_FIELD",
                    field_name=field.name,
                )
            field_names.add(field.name)

    def _resolve_schemas(self) -> SchemaConfig:
        if not self._schema_cache:
            raise SchemaError(
                "No schemas loaded",
                error_code="NO_SCHEMAS",
            )

        self._check_all_cycles()

        resolved = {}
        for name, raw in self._schema_cache.items():
            resolved[name] = self._resolve_inheritance(name, raw, depth=0)

        target_name = getattr(self, "_target_schema_name", None)
        if not target_name:
            target_name = next(iter(resolved))
        return self._build_schema_config(target_name, resolved)

    def _resolve_inheritance(
        self, schema_name: str, raw_schema: dict, depth: int
    ) -> dict:
        if depth > self.MAX_INHERITANCE_DEPTH:
            raise SchemaError(
                f"Maximum inheritance depth ({self.MAX_INHERITANCE_DEPTH}) exceeded for schema '{schema_name}'",
                error_code="MAX_DEPTH_EXCEEDED",
            )

        schema = deepcopy(raw_schema)
        base = schema.get("base")

        if base is None:
            schema["resolved_fields"] = schema.get("fields", [])
            return schema

        bases = [base] if isinstance(base, str) else base
        resolved_fields = []
        child_field_names = {
            f.get("name") if isinstance(f, dict) else f.name
            for f in schema.get("fields", [])
        }

        base_schemas = []
        for base_name in bases:
            if base_name not in self._schema_cache:
                raise SchemaError(
                    f"Base schema '{base_name}' not found for schema '{schema_name}'",
                    error_code="BASE_NOT_FOUND",
                    field_name="base",
                )
            base_raw = self._schema_cache[base_name]
            base_schema = self._resolve_inheritance(base_name, base_raw, depth + 1)
            base_schemas.append(base_schema)

        for base_schema in base_schemas:
            for field in base_schema.get("resolved_fields", []):
                if isinstance(field, dict):
                    field = FieldDefinition(**field)
                if field.name not in child_field_names:
                    resolved_fields.append(field)

        for field in schema.get("fields", []):
            if isinstance(field, dict):
                field = FieldDefinition(**field)
            resolved_fields.append(field)

        schema["resolved_fields"] = resolved_fields
        return schema

    def _build_schema_config(
        self, name: str, resolved: dict[str, dict]
    ) -> SchemaConfig:
        raw = resolved[name]
        fields = raw.get("resolved_fields", [])

        if isinstance(fields[0], dict) if fields else False:
            fields = [FieldDefinition(**f) for f in fields]

        schema_dict = {
            "name": raw["name"],
            "version": raw["version"],
            "description": raw.get("description"),
            "fields": fields,
            "base": raw.get("base"),
            "metadata": raw.get("metadata"),
        }

        return SchemaConfig(**schema_dict)

    def _build_dependency_graph(self) -> dict[str, set[str]]:
        graph = defaultdict(set)
        for name, raw in self._schema_cache.items():
            base = raw.get("base")
            if base is None:
                continue
            bases = [base] if isinstance(base, str) else base
            for b in bases:
                graph[name].add(b)
        return graph

    def _check_all_cycles(self) -> None:
        graph = self._build_dependency_graph()
        all_schemas = set(self._schema_cache.keys())

        for schema_name in all_schemas:
            cycle_result = self._detect_cycle(graph, schema_name)
            if cycle_result:
                path, start_idx = cycle_result
                if len(set(path[start_idx:])) < len(path[start_idx:]):
                    raise SchemaError(
                        f"Circular inheritance detected in schema '{schema_name}'",
                        error_code="CYCLE_DETECTED",
                        cycle_path=path,
                    )

        for schema_name in all_schemas:
            self._check_multi_schema_cycles(graph, schema_name, set())

    def _detect_cycle(
        self, graph: dict[str, set[str]], start: str
    ) -> Optional[tuple[list[str], int]]:
        visited = set()
        recursion_stack = []
        start_indices = {}

        def dfs(node: str) -> Optional[tuple[list[str], int]]:
            visited.add(node)
            recursion_stack.append(node)
            start_indices[node] = len(recursion_stack) - 1

            for neighbor in graph.get(node, set()):
                if neighbor not in visited:
                    result = dfs(neighbor)
                    if result:
                        return result
                elif neighbor in start_indices:
                    idx = start_indices[neighbor]
                    return (recursion_stack[idx:] + [neighbor], idx)

            del start_indices[node]
            recursion_stack.pop()
            return None

        return dfs(start)

    def _check_multi_schema_cycles(
        self, graph: dict[str, set[str]], start: str, visited: set[str]
    ) -> None:
        if start in visited:
            cycle_path = list(visited)
            raise SchemaError(
                f"Circular inheritance detected involving schema '{start}'",
                error_code="CIRCULAR_INHERITANCE",
                cycle_path=cycle_path,
            )

        visited.add(start)

        for neighbor in graph.get(start, set()):
            if neighbor in self._schema_cache:
                self._check_multi_schema_cycles(graph, neighbor, visited.copy())


def load_schema(source: Union[str, Path, dict]) -> SchemaConfig:
    parser = SchemaParser()
    return parser.load(source)
