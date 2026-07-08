"""EntityFormScreen — schema-driven create/edit form with validation feedback."""

from __future__ import annotations

from typing import Any

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, Select, Static

from mosaic.tui.backend.protocol import (
    SYSTEM_FIELDS,
    BackendError,
    EntityTypeSchema,
    FieldInfo,
    TUIBackend,
)

_BOOL_OPTIONS = [("true", "true"), ("false", "false")]
_TRUE_STRINGS = frozenset({"true", "1", "yes", "y"})
_FALSE_STRINGS = frozenset({"false", "0", "no", "n"})

_INT_TYPES = frozenset({"integer"})
_FLOAT_TYPES = frozenset({"float", "double", "decimal"})


class FieldCoercionError(ValueError):
    """Raised when a raw form value cannot be coerced to the slot's range."""


def coerce_scalar(field: FieldInfo, raw: str) -> Any:
    """Coerce one scalar string to the LinkML range of *field*."""
    raw = raw.strip()
    if field.field_type in _INT_TYPES:
        try:
            return int(raw)
        except ValueError as exc:
            raise FieldCoercionError(
                f"{field.name}: {raw!r} is not an integer"
            ) from exc
    if field.field_type in _FLOAT_TYPES:
        try:
            return float(raw)
        except ValueError as exc:
            raise FieldCoercionError(
                f"{field.name}: {raw!r} is not a number"
            ) from exc
    if field.field_type == "boolean":
        lowered = raw.lower()
        if lowered in _TRUE_STRINGS:
            return True
        if lowered in _FALSE_STRINGS:
            return False
        raise FieldCoercionError(f"{field.name}: {raw!r} is not a boolean")
    # strings, dates, datetimes, enums, and refs pass through as strings
    return raw


def coerce_field(field: FieldInfo, raw: str) -> Any:
    """Coerce a raw input string to the slot's range.

    Returns ``None`` for empty input. Multivalued slots accept
    comma-separated values.

    Raises:
        FieldCoercionError: When the value does not fit the range.
    """
    raw = raw.strip()
    if not raw:
        return None
    if field.multivalued:
        return [coerce_scalar(field, part) for part in raw.split(",") if part.strip()]
    return coerce_scalar(field, raw)


def format_initial(value: Any) -> str:
    """Render an existing field value back into form-input text."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, list):
        return ", ".join(format_initial(v) for v in value)
    return str(value)


def editable_fields(entity_schema: EntityTypeSchema) -> list[FieldInfo]:
    """User-editable slots: everything except system/identifier fields."""
    system = set(SYSTEM_FIELDS)
    return [
        f
        for f in entity_schema.fields
        if f.name not in system and not f.identifier
    ]


class EntityFormScreen(ModalScreen[str | None]):
    """Modal create/edit form generated from the entity type's schema.

    Dismisses with the saved entity id, or ``None`` on cancel.

    Args:
        backend: The TUIBackend to write through.
        entity_type: The entity type being created/edited.
        entity_schema: Schema for the entity type (drives the controls).
        entity_id: When set, the form edits this entity (full replace).
        initial: Existing user-slot values to prefill (edit mode).
    """

    DEFAULT_CSS = """
    EntityFormScreen {
        align: center middle;
    }
    EntityFormScreen > VerticalScroll {
        width: 70;
        max-height: 80%;
        background: $surface;
        border: round $accent;
        padding: 1 2;
    }
    EntityFormScreen #form-title {
        text-style: bold;
        margin-bottom: 1;
    }
    EntityFormScreen .field-label {
        margin-top: 1;
    }
    EntityFormScreen .field-label .required {
        color: $text-error;
    }
    EntityFormScreen #form-error {
        color: $text-error;
        margin-top: 1;
        height: auto;
    }
    EntityFormScreen #form-buttons {
        margin-top: 1;
        height: 3;
        align-horizontal: right;
    }
    EntityFormScreen Button {
        margin-left: 2;
    }
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel", show=True),
        Binding("ctrl+s", "save", "Save", show=True),
    ]

    def __init__(
        self,
        backend: TUIBackend,
        entity_type: str,
        entity_schema: EntityTypeSchema,
        entity_id: str | None = None,
        initial: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self._backend = backend
        self._entity_type = entity_type
        self._entity_schema = entity_schema
        self._entity_id = entity_id
        self._initial = initial or {}
        self._fields = editable_fields(entity_schema)

    @property
    def is_edit(self) -> bool:
        return self._entity_id is not None

    def compose(self) -> ComposeResult:
        title = (
            f"Edit {self._entity_type} {self._entity_id}"
            if self.is_edit
            else f"New {self._entity_type}"
        )
        with VerticalScroll():
            yield Label(title, id="form-title")
            for field in self._fields:
                yield from self._compose_field(field)
            yield Static("", id="form-error")
            with Horizontal(id="form-buttons"):
                yield Button("Save", variant="primary", id="save-button")
                yield Button("Cancel", id="cancel-button")

    def _compose_field(self, field: FieldInfo) -> ComposeResult:
        required = " [red]*[/red]" if field.required else ""
        type_hint = field.field_type
        if field.ref_target:
            type_hint = f"ref → {field.ref_target}"
        if field.multivalued:
            type_hint += ", multivalued"
        yield Label(
            f"{field.name}{required}  [dim]({type_hint})[/dim]",
            classes="field-label",
        )

        initial = self._initial.get(field.name)
        if field.enum_values:
            options = [(v, v) for v in field.enum_values]
            value = initial if initial in field.enum_values else Select.BLANK
            yield Select(
                options,
                value=value,
                allow_blank=True,
                id=f"field-{field.name}",
            )
        elif field.field_type == "boolean" and not field.multivalued:
            value = format_initial(initial) if initial is not None else Select.BLANK
            yield Select(
                _BOOL_OPTIONS,
                value=value,
                allow_blank=True,
                id=f"field-{field.name}",
            )
        else:
            placeholder = field.field_type
            if field.ref_target:
                placeholder = f"UUID of a {field.ref_target}"
            if field.multivalued:
                placeholder += " (comma-separated)"
            yield Input(
                value=format_initial(initial),
                placeholder=placeholder,
                id=f"field-{field.name}",
            )

    # ------------------------------------------------------------------
    # Value collection
    # ------------------------------------------------------------------

    def _raw_value(self, field: FieldInfo) -> str:
        widget = self.query_one(f"#field-{field.name}")
        if isinstance(widget, Select):
            value = widget.value
            return "" if value is Select.BLANK else str(value)
        if isinstance(widget, Input):
            return widget.value
        return ""

    def collect_data(self) -> dict[str, Any]:
        """Collect, coerce, and validate form values.

        Raises:
            FieldCoercionError: On type errors or missing required fields.
        """
        data: dict[str, Any] = {}
        errors: list[str] = []
        for field in self._fields:
            raw = self._raw_value(field)
            try:
                value = coerce_field(field, raw)
            except FieldCoercionError as exc:
                errors.append(str(exc))
                continue
            if value is None:
                if field.required:
                    errors.append(f"{field.name}: required")
                continue
            data[field.name] = value
        if errors:
            raise FieldCoercionError("; ".join(errors))
        return data

    def _show_error(self, message: str) -> None:
        self.query_one("#form-error", Static).update(message)

    # ------------------------------------------------------------------
    # Actions / events
    # ------------------------------------------------------------------

    async def action_save(self) -> None:
        await self._save()

    def action_cancel(self) -> None:
        self.dismiss(None)

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "save-button":
            await self._save()
        elif event.button.id == "cancel-button":
            self.dismiss(None)

    async def _save(self) -> None:
        try:
            data = self.collect_data()
        except FieldCoercionError as exc:
            self._show_error(str(exc))
            return

        try:
            if self.is_edit:
                assert self._entity_id is not None
                await self._backend.update_entity(
                    self._entity_type, self._entity_id, data
                )
                saved_id = self._entity_id
            else:
                saved_id = await self._backend.create_entity(self._entity_type, data)
        except BackendError as exc:
            detail = f" — {exc.detail}" if exc.detail else ""
            self._show_error(f"{exc.message}{detail}")
            return
        self.dismiss(saved_id)
