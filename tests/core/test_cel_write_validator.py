"""Tests for CEL WriteValidator integration."""

import pytest
import tempfile
import os

from hippo.core.validators import CELWriteValidator
from hippo.core.validation.validators import WriteOperation


class TestCELWriteValidator:
    def test_write_validator_initialization(self):
        validator = CELWriteValidator()
        assert validator.get_engine() is None

    def test_write_validator_load_from_path(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(
                """validators:
  - name: test
    entity_types: [Sample]
    'on': [create]
    condition: "entity.name != ''"
"""
            )
            f.flush()
            validator = CELWriteValidator(validators_path=f.name)
            assert validator.get_engine() is not None
            assert validator.get_engine().is_loaded is True
            os.unlink(f.name)

    def test_write_validator_valid_operation(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(
                """validators:
  - name: name_required
    entity_types: [Sample]
    'on': [create]
    condition: "entity.name != ''"
"""
            )
            f.flush()
            validator = CELWriteValidator(validators_path=f.name)
            op = WriteOperation(
                operation="insert", entity_type="Sample", data={"name": "test"}
            )
            result = validator.validate(op)
            assert result.is_valid is True
            os.unlink(f.name)

    def test_write_validator_invalid_operation(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(
                """validators:
  - name: name_required
    entity_types: [Sample]
    'on': [create]
    condition: "entity.name != ''"
"""
            )
            f.flush()
            validator = CELWriteValidator(validators_path=f.name)
            op = WriteOperation(
                operation="insert", entity_type="Sample", data={"name": ""}
            )
            result = validator.validate(op)
            assert result.is_valid is False
            os.unlink(f.name)

    def test_write_validator_maps_insert_to_create(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(
                """validators:
  - name: create_only
    entity_types: [Sample]
    'on': [create]
    condition: "entity.name != ''"
"""
            )
            f.flush()
            validator = CELWriteValidator(validators_path=f.name)
            op = WriteOperation(
                operation="insert", entity_type="Sample", data={"name": ""}
            )
            result = validator.validate(op)
            assert result.is_valid is False
            os.unlink(f.name)

    def test_write_validator_not_loaded_returns_valid(self):
        validator = CELWriteValidator()
        op = WriteOperation(operation="insert", entity_type="Sample", data={"name": ""})
        result = validator.validate(op)
        assert result.is_valid is True
