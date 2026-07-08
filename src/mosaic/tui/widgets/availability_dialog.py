"""AvailabilityScreen — modal dialog for entity availability transitions.

Mosaic has no hard deletes: entities transition between lifecycle statuses
(``active``, ``archived``, ``superseded``, ``deleted``, ``distributed``,
``removed``) which map onto the ``is_available`` flag, with the driver
recorded in provenance.
"""

from __future__ import annotations

from typing import Any

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, Select, Static

from mosaic.tui.backend.protocol import AVAILABLE_STATUSES, STATUS_VALUES


def status_to_availability(status: str) -> bool:
    """Map a lifecycle status onto the ``is_available`` flag."""
    return status in AVAILABLE_STATUSES


def compose_reason(status: str, note: str) -> str:
    """Build the provenance reason string for a transition."""
    note = note.strip()
    return f"{status}: {note}" if note else status


class AvailabilityScreen(ModalScreen["tuple[bool, str] | None"]):
    """Modal availability transition dialog.

    Dismisses with ``(is_available, reason)`` or ``None`` on cancel.

    Args:
        entity_label: Short label of the entity being transitioned.
    """

    DEFAULT_CSS = """
    AvailabilityScreen {
        align: center middle;
    }
    AvailabilityScreen > Vertical {
        width: 56;
        height: auto;
        background: $surface;
        border: round $accent;
        padding: 1 2;
    }
    AvailabilityScreen #availability-title {
        text-style: bold;
        margin-bottom: 1;
    }
    AvailabilityScreen .row-label {
        margin-top: 1;
    }
    AvailabilityScreen #availability-hint {
        color: $text-muted;
        margin-top: 1;
        height: auto;
    }
    AvailabilityScreen #availability-buttons {
        margin-top: 1;
        height: 3;
        align-horizontal: right;
    }
    AvailabilityScreen Button {
        margin-left: 2;
    }
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel", show=True),
    ]

    def __init__(self, entity_label: str, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._entity_label = entity_label

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label(
                f"Availability transition — {self._entity_label}",
                id="availability-title",
            )
            yield Label("Status", classes="row-label")
            yield Select(
                [(s, s) for s in STATUS_VALUES],
                value=STATUS_VALUES[0],
                allow_blank=False,
                id="status-select",
            )
            yield Label("Reason (optional)", classes="row-label")
            yield Input(placeholder="Why is this changing?", id="reason-input")
            yield Static("", id="availability-hint")
            with Horizontal(id="availability-buttons"):
                yield Button("Apply", variant="primary", id="apply-button")
                yield Button("Cancel", id="cancel-button")

    def on_mount(self) -> None:
        self._update_hint(str(self.query_one("#status-select", Select).value))

    def _update_hint(self, status: str) -> None:
        available = status_to_availability(status)
        flag = (
            "[green]is_available = true[/green]"
            if available
            else "[red]is_available = false[/red]"
        )
        self.query_one("#availability-hint", Static).update(
            f"→ {flag} (no hard delete; recorded in provenance)"
        )

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id == "status-select" and event.value is not Select.BLANK:
            self._update_hint(str(event.value))

    def _apply(self) -> None:
        status = str(self.query_one("#status-select", Select).value)
        note = self.query_one("#reason-input", Input).value
        self.dismiss((status_to_availability(status), compose_reason(status, note)))

    def action_cancel(self) -> None:
        self.dismiss(None)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "apply-button":
            self._apply()
        elif event.button.id == "cancel-button":
            self.dismiss(None)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "reason-input":
            self._apply()
