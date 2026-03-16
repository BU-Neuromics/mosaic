"""CEL Validator Engine - CEL Condition Parser."""

import re
from typing import Any, Dict, Optional

from cel import evaluate

from hippo.core.validators.exceptions import CELParseError


class CELCondition:
    """Parses and compiles CEL condition expressions.

    Handles compilation of CEL expressions into reusable expression objects
    that can be evaluated against validation contexts.
    """

    def __init__(
        self,
        expression: str,
        line_number: Optional[int] = None,
        variables: Optional[list[str]] = None,
    ):
        """Initialize CEL condition.

        Args:
            expression: The CEL expression string.
            line_number: Line number in validators.yaml (for error reporting).
            variables: List of variable names to declare in CEL environment.

        Raises:
            CELParseError: If the expression fails to compile.
        """
        self.expression = expression
        self.line_number = line_number
        self._variables = variables or ["entity", "existing"]
        self._is_valid = False
        self._compile()

    def _compile(self) -> None:
        """Compile the CEL expression.

        For CEL, we skip syntax validation at compile time since the
        common-expression-language library handles this at evaluation.
        We just mark it as valid and catch errors at evaluation time.
        """
        self._is_valid = True

    def evaluate(self, context: Dict[str, Any]) -> Any:
        """Evaluate the compiled CEL expression.

        Args:
            context: Dictionary of variable bindings for evaluation.

        Returns:
            The result of CEL expression evaluation.

        Raises:
            CELEvaluationError: If evaluation fails at runtime.
        """
        if not self._is_valid:
            raise CELParseError(
                message="CEL expression not compiled",
                expression=self.expression,
            )

        try:
            return evaluate(self.expression, context)
        except Exception as e:
            error_str = str(e)
            if "No such key" in error_str or "undefined" in error_str.lower():
                return False
            from hippo.core.validators.exceptions import CELEvaluationError

            field_ref = self._extract_field_reference(error_str)
            raise CELEvaluationError(
                message=f"Failed to evaluate CEL expression: {e}",
                field_reference=field_ref,
                expression=self.expression,
            )

    def _extract_field_reference(self, error_msg: str) -> Optional[str]:
        """Extract field reference from error message.

        Args:
            error_msg: The error message string.

        Returns:
            The field reference if found, None otherwise.
        """
        match = re.search(r"undefined field ['\"]?(\w+)['\"]?", error_msg)
        if match:
            return match.group(1)
        return None

    @property
    def is_valid(self) -> bool:
        """Check if the expression was successfully compiled."""
        return self._is_valid
