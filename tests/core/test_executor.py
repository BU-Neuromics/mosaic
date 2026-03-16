"""Tests for ValidatorExecutor and related classes."""

import pytest

from hippo.core.validation import (
    ExecutorConfig,
    FeatureNotAvailableError,
    ValidationResult,
    ValidatorConfig,
    ValidatorContext,
    ValidatorExecutor,
    ValidationTimeoutError,
    WriteOperation,
    WriteValidator,
)


class TestValidatorContext:
    """Tests for ValidatorContext class."""

    def test_basic_context_creation(self):
        ctx = ValidatorContext(
            data={"name": "test"},
            entity_id="123",
            entity_type="Sample",
            operation="create",
        )
        assert ctx.data == {"name": "test"}
        assert ctx.entity_id == "123"
        assert ctx.entity_type == "Sample"
        assert ctx.operation == "create"

    def test_get_set_values(self):
        ctx = ValidatorContext(data={})
        ctx.set("key1", "value1")
        assert ctx.get("key1") == "value1"
        assert ctx.get("nonexistent", "default") == "default"

    def test_update_data(self):
        ctx = ValidatorContext(data={})
        ctx.update({"key1": "value1", "key2": "value2"})
        assert ctx.get("key1") == "value1"
        assert ctx.get("key2") == "value2"

    def test_to_dict(self):
        ctx = ValidatorContext(data={"name": "test"})
        ctx.set("extra", "value")
        result = ctx.to_dict()
        assert result == {"name": "test", "extra": "value"}

    def test_copy_is_isolated(self):
        original = ValidatorContext(data={"name": "test"}, entity_id="123")
        copy = original.copy()

        copy.data["name"] = "modified"
        copy.entity_id = "456"

        assert original.data["name"] == "test"
        assert original.entity_id == "123"


class DummyValidator(WriteValidator):
    """Test validator that returns configurable result."""

    def __init__(self, is_valid: bool = True, errors: list[str] | None = None):
        self._is_valid = is_valid
        self._errors = errors or []

    def validate(self, operation: WriteOperation) -> ValidationResult:
        return ValidationResult(is_valid=self._is_valid, errors=self._errors)


class TestValidatorExecutor:
    """Tests for ValidatorExecutor class."""

    def test_executor_empty_initially(self):
        executor = ValidatorExecutor()
        assert executor.get_validator_count() == 0

    def test_add_validator(self):
        executor = ValidatorExecutor()
        validator = DummyValidator()
        executor.add_validator(validator)
        assert executor.get_validator_count() == 1

    def test_execute_with_no_validators_returns_success(self):
        executor = ValidatorExecutor()
        op = WriteOperation(
            operation="insert", entity_type="sample", data={"id": "123"}
        )
        result = executor.execute(op)
        assert result.is_valid is True

    def test_execute_with_disabled_executor_returns_success(self):
        config = ExecutorConfig(enabled=False)
        executor = ValidatorExecutor(config=config)
        validator = DummyValidator(is_valid=False)
        executor.add_validator(validator)

        op = WriteOperation(
            operation="insert", entity_type="sample", data={"id": "123"}
        )
        result = executor.execute(op)
        assert result.is_valid is True

    def test_execute_fail_fast_on_failure(self):
        config = ExecutorConfig(fail_fast=True)
        executor = ValidatorExecutor(config=config)

        executor.add_validator(DummyValidator(is_valid=False, errors=["Error 1"]))
        executor.add_validator(DummyValidator(is_valid=False, errors=["Error 2"]))

        op = WriteOperation(
            operation="insert", entity_type="sample", data={"id": "123"}
        )
        result = executor.execute(op)

        assert result.is_valid is False
        assert "Error 1" in result.errors

    def test_execute_collects_all_errors_when_not_fail_fast(self):
        config = ExecutorConfig(fail_fast=False)
        executor = ValidatorExecutor(config=config)

        executor.add_validator(DummyValidator(is_valid=False, errors=["Error 1"]))
        executor.add_validator(DummyValidator(is_valid=False, errors=["Error 2"]))

        op = WriteOperation(
            operation="insert", entity_type="sample", data={"id": "123"}
        )
        result = executor.execute(op)

        assert result.is_valid is False
        assert "Error 1" in result.errors
        assert "Error 2" in result.errors

    def test_context_propagation_between_validators(self):
        executor = ValidatorExecutor()

        class ContextModifyingValidator(WriteValidator):
            def validate(self, operation: WriteOperation) -> ValidationResult:
                operation.data["modified"] = True
                return ValidationResult(is_valid=True)

        class CheckingValidator(WriteValidator):
            def validate(self, operation: WriteOperation) -> ValidationResult:
                if operation.data.get("modified"):
                    return ValidationResult(
                        is_valid=True,
                        errors=[],
                        entity_id=operation.data.get("id"),
                    )
                return ValidationResult(
                    is_valid=False,
                    errors=["Context not modified"],
                    entity_id=operation.data.get("id"),
                )

        executor.add_validator(ContextModifyingValidator())
        executor.add_validator(CheckingValidator())

        op = WriteOperation(
            operation="insert", entity_type="sample", data={"id": "123"}
        )
        result = executor.execute(op)
        assert result.is_valid is True

    def test_feature_dependency_resolution(self):
        def feature_resolver(feature: str) -> bool:
            return feature == "feature-001"

        executor = ValidatorExecutor(feature_resolver=feature_resolver)
        executor.add_validator(
            DummyValidator(),
            ValidatorConfig(name="test", features=["feature-001"]),
        )

        op = WriteOperation(
            operation="insert", entity_type="sample", data={"id": "123"}
        )
        result = executor.execute(op)
        assert result.is_valid is True

    def test_feature_dependency_missing_raises_error(self):
        def feature_resolver(feature: str) -> bool:
            return False

        executor = ValidatorExecutor(feature_resolver=feature_resolver)
        executor.add_validator(
            DummyValidator(),
            ValidatorConfig(name="test", features=["missing-feature"]),
        )

        op = WriteOperation(
            operation="insert", entity_type="sample", data={"id": "123"}
        )

        with pytest.raises(FeatureNotAvailableError):
            executor.execute(op)

    def test_clear_validators(self):
        executor = ValidatorExecutor()
        executor.add_validator(DummyValidator())
        assert executor.get_validator_count() == 1

        executor.clear_validators()
        assert executor.get_validator_count() == 0


class TestExecutorConfig:
    """Tests for ExecutorConfig class."""

    def test_default_config(self):
        config = ExecutorConfig()
        assert config.enabled is True
        assert config.fail_fast is True
        assert config.validate_config is True
        assert config.timeout_seconds is None

    def test_custom_config(self):
        config = ExecutorConfig(
            enabled=False,
            fail_fast=False,
            timeout_seconds=30.0,
        )
        assert config.enabled is False
        assert config.fail_fast is False
        assert config.timeout_seconds == 30.0


class TestValidatorConfig:
    """Tests for ValidatorConfig class."""

    def test_default_config(self):
        config = ValidatorConfig(name="test")
        assert config.name == "test"
        assert config.enabled is True
        assert config.timeout_seconds is None
        assert config.features == []
        assert config.config == {}

    def test_custom_config(self):
        config = ValidatorConfig(
            name="test",
            enabled=False,
            timeout_seconds=10.0,
            features=["feature-001", "feature-002"],
            config={"key": "value"},
        )
        assert config.enabled is False
        assert config.timeout_seconds == 10.0
        assert config.features == ["feature-001", "feature-002"]
        assert config.config == {"key": "value"}


class TestValidationTimeoutError:
    """Tests for ValidationTimeoutError exception."""

    def test_exception_attributes(self):
        error = ValidationTimeoutError(
            message="Timeout occurred",
            validator_name="TestValidator",
            timeout_seconds=5.0,
        )
        assert error.validator_name == "TestValidator"
        assert error.timeout_seconds == 5.0
        assert "Timeout" in str(error)


class TestFeatureNotAvailableError:
    """Tests for FeatureNotAvailableError exception."""

    def test_exception_attributes(self):
        error = FeatureNotAvailableError(
            message="Feature 'feature-001' is not available",
            feature_name="feature-001",
            reason="Not initialized",
        )
        assert error.feature_name == "feature-001"
        assert error.reason == "Not initialized"
        assert "feature-001" in str(error)


class TestEmptyValidatorConfiguration:
    """Tests for handling empty or missing validator configuration."""

    def test_executor_with_no_validators_returns_success(self):
        executor = ValidatorExecutor()
        op = WriteOperation(
            operation="insert", entity_type="sample", data={"id": "123"}
        )
        result = executor.execute(op)
        assert result.is_valid is True

    def test_load_validators_with_nonexistent_file(self):
        from hippo.core.validation.loader import load_validators

        valid, invalid, expanded = load_validators("/nonexistent/path.yaml")
        assert valid == []
        assert invalid == []
        assert expanded == []

    def test_load_validators_with_empty_validators_list(self, tmp_path):
        from hippo.core.validation.loader import load_validators
        import yaml

        validators_file = tmp_path / "validators.yaml"
        validators_file.write_text(yaml.dump({"validators": []}))

        valid, invalid, expanded = load_validators(str(validators_file))
        assert valid == []
        assert invalid == []
        assert expanded == []


class TestNestedRuleExpansion:
    """Tests for nested rule expansion logic."""

    def test_expand_nested_rules_with_no_expand(self):
        from hippo.core.validation.loader import expand_nested_rules

        config = {"name": "test_validator", "enabled": True}
        expanded = expand_nested_rules(config)
        assert len(expanded) == 1
        assert expanded[0]["name"] == "test_validator"

    def test_expand_nested_rules_with_expand(self):
        from hippo.core.validation.loader import expand_nested_rules

        config = {
            "name": "parent_validator",
            "enabled": True,
            "expand": [
                {"name": "child_validator_1", "condition": "entity.a > 0"},
                {"name": "child_validator_2", "condition": "entity.b > 0"},
            ],
        }
        expanded = expand_nested_rules(config)
        assert len(expanded) == 2
        assert expanded[0]["name"] == "child_validator_1"
        assert expanded[1]["name"] == "child_validator_2"

    def test_expand_nested_rules_preserves_base_config(self):
        from hippo.core.validation.loader import expand_nested_rules

        config = {
            "name": "parent_validator",
            "enabled": True,
            "entity_types": ["Sample"],
            "expand": [{"name": "child_validator"}],
        }
        expanded = expand_nested_rules(config)
        assert len(expanded) == 1
        assert expanded[0]["entity_types"] == ["Sample"]
