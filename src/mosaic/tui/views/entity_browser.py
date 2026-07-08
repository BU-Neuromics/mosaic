"""EntityBrowserView — paginated, filterable entity table with CRUD actions."""

from __future__ import annotations

from typing import Any

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import DataTable, Input, Label, Static

from mosaic.tui.backend.protocol import (
    BackendError,
    EntityTypeSchema,
    PagedResult,
    TUIBackend,
)
from mosaic.tui.render import format_timestamp, format_value, short_id

_PAGE_SIZE = 20
_MAX_COLS = 4  # first 4 user-defined fields


class EntityBrowserView(Widget):
    """Paginated entity browser with inline filter and CRUD actions.

    Args:
        entity_type: The entity type to browse.
        backend: The TUIBackend to fetch data from.
    """

    DEFAULT_CSS = """
    EntityBrowserView {
        height: 1fr;
    }
    EntityBrowserView #browser-title {
        height: 1;
        padding: 0 1;
        text-style: bold;
        color: $text-accent;
    }
    EntityBrowserView #entity-table {
        height: 1fr;
    }
    EntityBrowserView #browser-empty {
        height: 1fr;
        content-align: center middle;
        color: $text-muted;
        display: none;
    }
    EntityBrowserView.empty #entity-table {
        display: none;
    }
    EntityBrowserView.empty #browser-empty {
        display: block;
    }
    EntityBrowserView #browser-footer {
        height: 3;
        padding: 0 1;
    }
    EntityBrowserView #page-indicator {
        width: 24;
        padding-top: 1;
        color: $text-muted;
    }
    EntityBrowserView #filter-input {
        width: 1fr;
    }
    """

    BINDINGS = [
        Binding("right", "next_page", "Next page", show=True),
        Binding("left", "prev_page", "Prev page", show=True),
        Binding("f", "focus_filter", "Filter", show=True),
        Binding("r", "refresh_view", "Refresh", show=True),
        Binding("enter", "open_detail", "Detail", show=True),
        Binding("n", "new_entity", "New", show=True),
        Binding("e", "edit_entity", "Edit", show=True),
        Binding("a", "availability", "Availability", show=True),
        Binding("p", "provenance", "Provenance", show=True),
    ]

    _current_page: reactive[int] = reactive(1)
    _total_pages: reactive[int] = reactive(1)
    _filter_text: reactive[str] = reactive("")

    def __init__(self, entity_type: str, backend: TUIBackend, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._entity_type = entity_type
        self._backend = backend
        self._columns: list[str] = []
        self._rows: list[dict[str, Any]] = []
        self._total_items: int = 0

    def compose(self) -> ComposeResult:
        yield Label(f"{self._entity_type}", id="browser-title")
        yield DataTable(id="entity-table", cursor_type="row", zebra_stripes=True)
        yield Static(
            f"No {self._entity_type} entities found — press [b]n[/b] to create one.",
            id="browser-empty",
        )
        with Horizontal(id="browser-footer"):
            yield Label("Page 1 of 1", id="page-indicator")
            yield Input(placeholder="Filter… (text or field=value)", id="filter-input")

    async def on_mount(self) -> None:
        self.reload()

    # ------------------------------------------------------------------
    # Error reporting
    # ------------------------------------------------------------------

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
        """Reload the current page in a background worker."""
        self.run_worker(self._load_page(), exclusive=True, group="browser-load")

    async def _load_page(self) -> None:
        """Fetch the current page from the backend and refresh the DataTable."""
        if not self.is_mounted:
            return
        table = self.query_one(DataTable)
        table.loading = True
        try:
            result: PagedResult = await self._backend.list_entities(
                entity_type=self._entity_type,
                page=self._current_page,
                filter_text=self._filter_text,
            )
        except BackendError as exc:
            self._report_error(exc.message)
            return
        finally:
            if self.is_mounted:
                table.loading = False

        self._rows = result.items
        self._total_items = result.total_items
        self._total_pages = max(1, result.total_pages)
        if self._current_page > self._total_pages:
            self._current_page = self._total_pages

        await self._refresh_table(result)
        self._update_page_indicator()

    async def _schema_for_type(self) -> EntityTypeSchema | None:
        """Entity type schema from the app cache (or backend fallback)."""
        try:
            app = self.app
            if hasattr(app, "get_or_fetch_schema"):
                schema = await app.get_or_fetch_schema()
            else:
                schema = await self._backend.get_schema()
        except BackendError as exc:
            self._report_error(exc.message)
            return None
        return schema.get_entity_type(self._entity_type)

    def _pick_columns(self, items: list[dict[str, Any]]) -> list[str]:
        """First user-defined fields shown as columns (sample-data driven)."""
        sample_data = items[0].get("data", {}) if items else {}
        return list(sample_data.keys())[:_MAX_COLS]

    async def _refresh_table(self, result: PagedResult) -> None:
        """Rebuild DataTable columns and rows from *result*."""
        table = self.query_one(DataTable)
        table.clear(columns=True)

        if not result.items:
            self.add_class("empty")
            return
        self.remove_class("empty")

        user_fields = self._pick_columns(result.items)
        cols = ["id", *user_fields, "created_at"]
        self._columns = cols
        for col in cols:
            table.add_column(col, key=col)

        for item in result.items:
            data = item.get("data", {})
            row = []
            for col in cols:
                if col == "id":
                    row.append(short_id(item.get("id", ""), 12))
                elif col == "created_at":
                    row.append(format_timestamp(item.get("created_at", "")))
                else:
                    row.append(format_value(data.get(col)))
            table.add_row(*row, key=str(item.get("id", "")))

    def _update_page_indicator(self) -> None:
        try:
            label = self.query_one("#page-indicator", Label)
            label.update(
                f"Page {self._current_page} of {self._total_pages}"
                f"  ({self._total_items})"
            )
        except Exception:  # noqa: BLE001 — not mounted
            pass

    def _selected_entity_id(self) -> str | None:
        """Entity id of the highlighted DataTable row, if any."""
        try:
            table = self.query_one(DataTable)
        except Exception:  # noqa: BLE001 — not mounted
            return None
        if table.cursor_row is None or table.cursor_row >= len(self._rows):
            return None
        return str(self._rows[table.cursor_row].get("id", "")) or None

    # ------------------------------------------------------------------
    # Actions — navigation
    # ------------------------------------------------------------------

    async def action_next_page(self) -> None:
        if self._current_page < self._total_pages:
            self._current_page += 1
            await self._load_page()

    async def action_prev_page(self) -> None:
        if self._current_page > 1:
            self._current_page -= 1
            await self._load_page()

    def action_focus_filter(self) -> None:
        try:
            self.query_one("#filter-input", Input).focus()
        except Exception:  # noqa: BLE001 — not mounted
            pass

    async def action_refresh_view(self) -> None:
        await self._load_page()

    async def action_open_detail(self) -> None:
        """Open the detail screen for the highlighted row."""
        entity_id = self._selected_entity_id()
        if entity_id:
            self._open_detail(entity_id)

    def _open_detail(self, entity_id: str) -> None:
        app = self.app
        if hasattr(app, "open_entity_detail"):
            app.open_entity_detail(self._entity_type, entity_id)

    # ------------------------------------------------------------------
    # Actions — CRUD
    # ------------------------------------------------------------------

    async def action_new_entity(self) -> None:
        """Open a schema-driven create form for this entity type."""
        from mosaic.tui.views.entity_form import EntityFormScreen

        entity_schema = await self._schema_for_type()
        if entity_schema is None:
            self._report_error(f"No schema available for {self._entity_type}")
            return

        def on_saved(entity_id: str | None) -> None:
            if entity_id:
                self.notify(f"Created {self._entity_type} {short_id(entity_id)}")
                self.reload()

        await self.app.push_screen(
            EntityFormScreen(
                backend=self._backend,
                entity_type=self._entity_type,
                entity_schema=entity_schema,
            ),
            on_saved,
        )

    async def action_edit_entity(self) -> None:
        """Open a schema-driven edit form for the highlighted row."""
        from mosaic.tui.views.entity_form import EntityFormScreen

        entity_id = self._selected_entity_id()
        if entity_id is None:
            return
        entity_schema = await self._schema_for_type()
        if entity_schema is None:
            self._report_error(f"No schema available for {self._entity_type}")
            return
        try:
            detail = await self._backend.get_entity(self._entity_type, entity_id)
        except BackendError as exc:
            self._report_error(exc.message)
            return

        def on_saved(saved_id: str | None) -> None:
            if saved_id:
                self.notify(f"Updated {self._entity_type} {short_id(saved_id)}")
                self.reload()

        await self.app.push_screen(
            EntityFormScreen(
                backend=self._backend,
                entity_type=self._entity_type,
                entity_schema=entity_schema,
                entity_id=entity_id,
                initial=detail.data,
            ),
            on_saved,
        )

    async def action_availability(self) -> None:
        """Open the availability transition dialog for the highlighted row."""
        from mosaic.tui.widgets.availability_dialog import AvailabilityScreen

        entity_id = self._selected_entity_id()
        if entity_id is None:
            return

        async def on_result(result: tuple[bool, str] | None) -> None:
            if result is None:
                return
            is_available, reason = result
            try:
                await self._backend.set_availability(
                    self._entity_type, entity_id, is_available, reason
                )
            except BackendError as exc:
                self._report_error(exc.message)
                return
            self.notify(f"Availability updated: {reason}")
            self.reload()

        await self.app.push_screen(
            AvailabilityScreen(entity_label=short_id(entity_id, 12)), on_result
        )

    async def action_provenance(self) -> None:
        """Open the provenance history screen for the highlighted row."""
        from mosaic.tui.views.provenance import ProvenanceScreen

        entity_id = self._selected_entity_id()
        if entity_id is None:
            return
        await self.app.push_screen(
            ProvenanceScreen(
                backend=self._backend,
                entity_type=self._entity_type,
                entity_id=entity_id,
            )
        )

    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------

    async def on_input_changed(self, event: Input.Changed) -> None:
        """Live-update table as filter text changes."""
        if event.input.id == "filter-input":
            self._filter_text = event.value
            self._current_page = 1  # Reset to page 1 on filter change
            self.reload()

    async def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Enter on a row opens the detail screen."""
        if event.row_key is not None and event.row_key.value:
            self._open_detail(str(event.row_key.value))
