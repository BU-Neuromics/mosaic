"""CEL Validator Engine - Main Validator Engine."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from hippo.core.validators.conditions import CELCondition
from hippo.core.validators.context import ValidationContext
from hippo.core.validators.exceptions import (
    CELParseError,
    CELEvaluationError,
    ValidationError,
)


def _entity_type_from_data(data: Dict[str, Any]) -> Optional[str]:
    """Extract entity type from entity data."""
    return data.get("__type__") or data.get("entity_type")


@dataclass
class ValidatorRule:
    """Represents a single validator rule from validators.yaml."""

    name: str
    entity_types: Optional[List[str]] = None
    on: List[str] = field(default_factory=lambda: ["create", "update", "delete"])
    priority: int = 0
    when: Optional[str] = None
    condition: Optional[str] = None
    error: str = "Validation failed: {name}"
    expand: List[Dict[str, str]] = field(default_factory=list)
    _cel_condition: Optional[CELCondition] = field(default=None, repr=False)
    _when_condition: Optional[CELCondition] = field(default=None, repr=False)


@dataclass
class ValidationResult:
    """Result of a validation operation."""

    is_valid: bool
    errors: List[Dict[str, Any]] = field(default_factory=list)

    def add_error(
        self,
        rule_name: str,
        message: str,
        entity_type: Optional[str] = None,
        entity_id: Optional[str] = None,
    ) -> None:
        """Add a validation error."""
        self.errors.append(
            {
                "rule": rule_name,
                "message": message,
                "entity_type": entity_type,
                "entity_id": entity_id,
            }
        )
        self.is_valid = False


class ValidatorEngine:
    """Main CEL validator engine for evaluating validation rules.

    Loads validator rules from validators.yaml and evaluates CEL conditions
    against entity data.
    """

    def __init__(self):
        """Initialize the validator engine."""
        self._rules: List[ValidatorRule] = []
        self._is_loaded = False

    def load(self, validators_path: str) -> None:
        """Load and parse validators from YAML file.

        Args:
            validators_path: Path to validators.yaml file.

        Raises:
            ValidationError: If YAML is invalid or contains errors.
        """
        path = Path(validators_path)
        if not path.exists():
            raise ValidationError(f"Validators file not found: {validators_path}")

        try:
            with open(path, "r") as f:
                data = yaml.safe_load(f)
        except yaml.YAMLError as e:
            raise ValidationError(f"Invalid YAML in validators file: {e}")

        self._validate_structure(data)
        self._parse_rules(data, path)
        self._is_loaded = True

    def _validate_structure(self, data: Any) -> None:
        """Validate the YAML structure.

        Args:
            data: Parsed YAML data.

        Raises:
            ValidationError: If structure is invalid.
        """
        if not isinstance(data, dict):
            raise ValidationError("Validators file must be a dictionary")

        if "validators" not in data:
            raise ValidationError("Missing 'validators' key in validators file")

        validators = data["validators"]
        if not isinstance(validators, list):
            raise ValidationError("'validators' must be a list")

    def _parse_rules(self, data: Dict[str, Any], path: Path) -> None:
        """Parse validator rules from YAML data.

        Args:
            data: Parsed YAML data.
            path: Path to validators file (for line number tracking).

        Raises:
            CELParseError: If CEL expressions fail to parse.
        """
        validators = data.get("validators", [])
        self._rules = []

        for idx, validator in enumerate(validators):
            if not isinstance(validator, dict):
                raise ValidationError(f"Validator at index {idx} must be a dictionary")

            name = validator.get("name")
            if not name:
                raise ValidationError(
                    f"Validator at index {idx} missing required 'name'"
                )

            condition = validator.get("condition")
            when = validator.get("when")

            rule = ValidatorRule(
                name=name,
                entity_types=validator.get("entity_types"),
                on=validator.get("on", ["create", "update", "delete"]),
                priority=validator.get("priority", 0),
                when=when,
                condition=condition,
                error=validator.get("error", "Validation failed: {name}"),
                expand=validator.get("expand", []),
            )

            if condition:
                line_number = self._estimate_line_number(path, idx)
                rule._cel_condition = CELCondition(condition, line_number=line_number)

            if when:
                line_number = self._estimate_line_number(path, idx)
                rule._when_condition = CELCondition(when, line_number=line_number)

            self._rules.append(rule)

    def _estimate_line_number(self, path: Path, validator_index: int) -> int:
        """Estimate line number for a validator.

        This is approximate since YAML doesn't track line numbers by default.

        Args:
            path: Path to validators file.
            validator_index: Index of the validator.

        Returns:
            Estimated line number.
        """
        try:
            with open(path, "r") as f:
                lines = f.readlines()
            return min(validator_index * 10 + 1, len(lines))
        except Exception:
            return validator_index + 1

    def evaluate(
        self,
        condition: str,
        context: ValidationContext,
    ) -> Any:
        """Evaluate a single CEL condition.

        Args:
            condition: The CEL expression string.
            context: Validation context.

        Returns:
            The evaluation result.

        Raises:
            CELParseError: If condition fails to parse.
            CELEvaluationError: If evaluation fails at runtime.
        """
        cel_cond = CELCondition(condition)
        return cel_cond.evaluate(context.to_dict())

    def validate(
        self,
        entity_type: str,
        operation: str,
        entity_data: Dict[str, Any],
        existing_entity: Optional[Dict[str, Any]] = None,
        entity_id: Optional[str] = None,
    ) -> ValidationResult:
        """Validate entity data against loaded rules.

        Args:
            entity_type: The type of entity being validated.
            operation: The operation type (create, update, delete).
            entity_data: The entity data to validate.
            existing_entity: Existing entity data (for updates).
            entity_id: The entity ID (for error messages).

        Returns:
            ValidationResult with success/failure information.
        """
        if not self._is_loaded:
            return ValidationResult(
                is_valid=False,
                errors=[{"rule": "system", "message": "Validator engine not loaded"}],
            )

        result = ValidationResult(is_valid=True)
        applicable_rules = self._get_applicable_rules(entity_type, operation)

        for rule in applicable_rules:
            if not self._evaluate_rule(
                rule, entity_data, existing_entity, entity_id, result
            ):
                pass

        return result

    def _get_applicable_rules(
        self, entity_type: str, operation: str
    ) -> List[ValidatorRule]:
        """Get rules applicable to an entity type and operation.

        Args:
            entity_type: The entity type.
            operation: The operation type.

        Returns:
            List of applicable rules sorted by priority.
        """
        applicable = []
        for rule in self._rules:
            if operation not in rule.on:
                continue

            if rule.entity_types is not None:
                if not self._is_entity_type_matching(entity_type, rule.entity_types):
                    continue

            applicable.append(rule)

        return sorted(applicable, key=lambda r: r.priority)

    def _is_entity_type_matching(
        self, entity_type: str, target_types: List[str]
    ) -> bool:
        """Check if entity type matches target types.

        Args:
            entity_type: The entity type to check.
            target_types: Target types from validator rule.

        Returns:
            True if entity type matches or is a subtype.
        """
        return entity_type in target_types

    def _evaluate_rule(
        self,
        rule: ValidatorRule,
        entity_data: Dict[str, Any],
        existing_entity: Optional[Dict[str, Any]],
        entity_id: Optional[str],
        result: ValidationResult,
    ) -> bool:
        """Evaluate a single validation rule.

        Args:
            rule: The validator rule.
            entity_data: The entity data.
            existing_entity: Existing entity data.
            entity_id: The entity ID.
            result: Validation result to update.

        Returns:
            True if validation passed, False otherwise.
        """
        context = ValidationContext(entity_data, existing_entity)

        if rule._when_condition is not None:
            try:
                when_result = rule._when_condition.evaluate(context.to_dict())
                if not bool(when_result):
                    return True
            except CELEvaluationError as e:
                result.add_error(
                    rule_name=rule.name,
                    message=f"Error evaluating 'when' condition: {e}",
                    entity_id=entity_id,
                )
                return False

        if rule._cel_condition is None:
            return True

        try:
            eval_result = rule._cel_condition.evaluate(context.to_dict())
            if not bool(eval_result):
                error_msg = rule.error.format(
                    name=rule.name,
                    entity_type=_entity_type_from_data(entity_data),
                    entity_id=entity_id,
                )
                result.add_error(
                    rule_name=rule.name,
                    message=error_msg,
                    entity_id=entity_id,
                )
                return False
        except CELEvaluationError as e:
            result.add_error(
                rule_name=rule.name,
                message=f"Error evaluating condition: {e}",
                entity_id=entity_id,
            )
            return False

        return True

    @property
    def rules(self) -> List[ValidatorRule]:
        """Get loaded validator rules."""
        return self._rules

    @property
    def is_loaded(self) -> bool:
        """Check if validators have been loaded."""
        return self._is_loaded
