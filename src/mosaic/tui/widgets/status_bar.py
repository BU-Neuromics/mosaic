"""StatusBar widget — backend mode, connection state, entity count, errors."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Label

from mosaic.tui.backend.protocol import ConnectionInfo


class StatusBar(Widget):
    """A single-line status bar displayed at the bottom of the TUI.

    Shows:
    - Connection indicator (``●`` green when reachable, red otherwise)
    - Backend mode (``sdk`` or ``rest``)
    - Connection target (SQLite file path or base URL)
    - Current entity count (when an entity type is selected)
    - Error messages (e.g. REST connection failures)
    """

    DEFAULT_CSS = """
    StatusBar {
        height: 1;
        background: $panel;
        color: $text-muted;
        dock: bottom;
        padding: 0 1;
    }
    StatusBar Label {
        width: 100%;
    }
    StatusBar.error Label {
        color: $text-error;
    }
    """

    entity_count: reactive[int] = reactive(0)
    _backend_mode: str = ""
    _connection_target: str = ""
    _connection_ok: bool | None = None
    _connection_detail: str = ""
    _error_message: str = ""

    def compose(self) -> ComposeResult:
        yield Label(self._build_text(), id="status-label")

    def _build_text(self) -> str:
        if self._error_message:
            return f"ERROR: {self._error_message}"
        parts = []
        if self._connection_ok is not None:
            parts.append("[green]●[/green]" if self._connection_ok else "[red]●[/red]")
        if self._backend_mode:
            parts.append(self._backend_mode)
        if self._connection_target:
            parts.append(self._connection_target)
        if self._connection_detail:
            parts.append(self._connection_detail)
        base = " | ".join(parts)
        if self.entity_count:
            base += f"  [{self.entity_count} entities]"
        return base or "Mosaic TUI"

    def set_backend(self, mode: str, target: str) -> None:
        """Update the backend mode and connection target label."""
        self._backend_mode = mode
        self._connection_target = target
        self._error_message = ""
        self.remove_class("error")
        self._refresh_label()

    def set_connection(self, info: ConnectionInfo) -> None:
        """Update the connection state from a backend probe."""
        self._backend_mode = info.mode
        self._connection_target = info.target
        self._connection_ok = info.ok
        self._connection_detail = info.detail if info.ok else ""
        if info.ok:
            self._error_message = ""
            self.remove_class("error")
        self._refresh_label()

    def set_error(self, message: str) -> None:
        """Display an error message (e.g. REST connection failure)."""
        self._error_message = message
        self.add_class("error")
        self._refresh_label()

    def clear_error(self) -> None:
        """Clear any displayed error message."""
        self._error_message = ""
        self.remove_class("error")
        self._refresh_label()

    def watch_entity_count(self, count: int) -> None:
        """Reactively update label when entity_count changes."""
        self._refresh_label()

    def _refresh_label(self) -> None:
        try:
            label = self.query_one("#status-label", Label)
            label.update(self._build_text())
        except Exception:  # noqa: BLE001 — not mounted yet
            pass
