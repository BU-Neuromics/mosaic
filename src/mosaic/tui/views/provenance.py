"""ProvenanceScreen — full provenance history for one entity."""

from __future__ import annotations

from typing import Any

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import DataTable, Footer, Label, Pretty, Static

from mosaic.tui.backend.protocol import BackendError, ProvenanceEvent, TUIBackend
from mosaic.tui.render import format_timestamp


class ProvenanceScreen(Screen):
    """Full provenance history (newest first) with per-event payload view.

    Args:
        backend: The TUIBackend to fetch history from.
        entity_type: The entity's type.
        entity_id: The entity's id.
    """

    DEFAULT_CSS = """
    ProvenanceScreen #provenance-title {
        height: 1;
        padding: 0 1;
        text-style: bold;
        color: $text-accent;
    }
    ProvenanceScreen #provenance-table {
        height: 2fr;
    }
    ProvenanceScreen #diff-header {
        height: 1;
        padding: 0 1;
        color: $text-muted;
        text-style: bold;
    }
    ProvenanceScreen #diff-panel {
        height: 1fr;
        border-top: solid $panel;
        padding: 0 1;
        overflow-y: auto;
    }
    ProvenanceScreen #provenance-empty {
        height: 1fr;
        content-align: center middle;
        color: $text-muted;
        display: none;
    }
    ProvenanceScreen.empty #provenance-table {
        display: none;
    }
    ProvenanceScreen.empty #provenance-empty {
        display: block;
    }
    """

    BINDINGS = [
        Binding("escape", "go_back", "Back", show=True),
        Binding("r", "refresh", "Refresh", show=True),
    ]

    def __init__(
        self,
        backend: TUIBackend,
        entity_type: str,
        entity_id: str,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self._backend = backend
        self._entity_type = entity_type
        self._entity_id = entity_id
        self._events: list[ProvenanceEvent] = []

    def compose(self) -> ComposeResult:
        yield Label(
            f"Provenance — {self._entity_type}: {self._entity_id}",
            id="provenance-title",
        )
        with Vertical():
            yield DataTable(id="provenance-table", cursor_type="row")
            yield Static("(no provenance events)", id="provenance-empty")
            yield Label("Event payload", id="diff-header")
            yield Pretty({}, id="diff-panel")
        yield Footer()

    async def on_mount(self) -> None:
        self.reload()

    def _report_error(self, message: str) -> None:
        app = self.app
        if hasattr(app, "report_error"):
            app.report_error(message)
        else:
            self.notify(message, severity="error")

    # ------------------------------------------------------------------
    # Data loading
    # ------------------------------------------------------------------

    def reload(self) -> None:
        """Reload the provenance history in a background worker."""
        self.run_worker(self._load(), exclusive=True, group="provenance-load")

    async def _load(self) -> None:
        if not self.is_mounted:
            return
        table = self.query_one("#provenance-table", DataTable)
        table.loading = True
        try:
            self._events = await self._backend.get_provenance(
                self._entity_type, self._entity_id
            )
        except BackendError as exc:
            self._report_error(exc.message)
            return
        finally:
            if self.is_mounted:
                table.loading = False
        self._render_events()

    def _render_events(self) -> None:
        table = self.query_one("#provenance-table", DataTable)
        table.clear(columns=True)
        if not self._events:
            self.add_class("empty")
            self.query_one("#diff-panel", Pretty).update({})
            return
        self.remove_class("empty")

        table.add_column("#", key="index", width=4)
        table.add_column("Timestamp", key="timestamp", width=22)
        table.add_column("Operation", key="operation", width=14)
        table.add_column("Actor", key="actor")
        total = len(self._events)
        for index, event in enumerate(self._events):
            table.add_row(
                str(total - index),
                format_timestamp(event.timestamp),
                event.event_type,
                event.actor or "",
                key=str(index),
            )
        self._show_event(0)

    def _show_event(self, index: int) -> None:
        if 0 <= index < len(self._events):
            self.query_one("#diff-panel", Pretty).update(self._events[index].diff)

    # ------------------------------------------------------------------
    # Actions / events
    # ------------------------------------------------------------------

    def action_go_back(self) -> None:
        self.app.pop_screen()

    async def action_refresh(self) -> None:
        self.reload()

    def on_data_table_row_highlighted(
        self, event: DataTable.RowHighlighted
    ) -> None:
        if event.row_key is not None and event.row_key.value is not None:
            self._show_event(int(event.row_key.value))
