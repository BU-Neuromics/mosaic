"""QueryView — structured field filters and full-text search over entities."""

from __future__ import annotations

from typing import Any

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import DataTable, Input, Label, Select, Static

from mosaic.tui.backend.protocol import (
    BackendError,
    PagedResult,
    SchemaView,
    TUIBackend,
)
from mosaic.tui.render import format_timestamp, format_value, short_id

_MAX_COLS = 4


def parse_filters(text: str) -> list[dict[str, Any]]:
    """Parse ``field=value, field2=value2`` into QueryEngine filters.

    Raises:
        ValueError: When a clause has no ``=`` or an empty field name.
    """
    filters: list[dict[str, Any]] = []
    for clause in text.split(","):
        clause = clause.strip()
        if not clause:
            continue
        field, sep, value = clause.partition("=")
        field = field.strip()
        if not sep or not field:
            raise ValueError(
                f"Bad filter {clause!r} — expected field=value"
            )
        filters.append({"field": field, "value": value.strip()})
    return filters


class QueryView(Widget):
    """Query screen exposing the QueryEngine (SDK) / search (REST) surface.

    Structured field filters (with and/or composition) are shown when the
    backend supports them; full-text search is shown when the backend has
    FTS. Results land in a paginated table; Enter opens the detail screen.

    Args:
        backend: The TUIBackend to query.
        schema: The schema view (for the entity type selector).
    """

    DEFAULT_CSS = """
    QueryView {
        height: 1fr;
    }
    QueryView #query-title {
        height: 1;
        padding: 0 1;
        text-style: bold;
        color: $text-accent;
    }
    QueryView .query-row {
        height: 3;
        padding: 0 1;
    }
    QueryView #entity-type-select {
        width: 32;
    }
    QueryView #filter-mode-select {
        width: 12;
    }
    QueryView #filters-input, QueryView #fts-input {
        width: 1fr;
    }
    QueryView #results-table {
        height: 1fr;
    }
    QueryView #query-status {
        height: 1;
        padding: 0 1;
        color: $text-muted;
    }
    """

    BINDINGS = [
        Binding("right", "next_page", "Next page", show=True),
        Binding("left", "prev_page", "Prev page", show=True),
        Binding("enter", "open_detail", "Detail", show=True),
    ]

    _current_page: reactive[int] = reactive(1)
    _total_pages: reactive[int] = reactive(1)

    def __init__(self, backend: TUIBackend, schema: SchemaView, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._backend = backend
        self._schema = schema
        self._rows: list[dict[str, Any]] = []
        self._mode: str = "filters"  # which input ran the last query

    def compose(self) -> ComposeResult:
        caps = self._backend.capabilities()
        type_options = [(et.name, et.name) for et in self._schema.entity_types]

        yield Label("Query", id="query-title")
        with Horizontal(classes="query-row"):
            yield Select(
                type_options,
                value=type_options[0][1] if type_options else Select.BLANK,
                allow_blank=not type_options,
                prompt="Entity type",
                id="entity-type-select",
            )
            yield Select(
                [("AND", "and"), ("OR", "or")],
                value="and",
                allow_blank=False,
                id="filter-mode-select",
            )
        if caps.supports_filters:
            with Horizontal(classes="query-row"):
                yield Input(
                    placeholder="Filters: field=value, field2=value2  (Enter to run)",
                    id="filters-input",
                )
        else:
            yield Static(
                "  Field filters are not exposed by the REST API — "
                "use full-text search below.",
                id="filters-unsupported",
            )
        if caps.supports_fts:
            with Horizontal(classes="query-row"):
                yield Input(
                    placeholder="Full-text search…  (Enter to run)",
                    id="fts-input",
                )
        yield DataTable(id="results-table", cursor_type="row", zebra_stripes=True)
        yield Label("No query run yet.", id="query-status")

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
    # Query execution
    # ------------------------------------------------------------------

    def _selected_type(self) -> str | None:
        value = self.query_one("#entity-type-select", Select).value
        return None if value is Select.BLANK else str(value)

    def run_query(self) -> None:
        """Run the current query in a background worker."""
        self.run_worker(self._run_query(), exclusive=True, group="query-run")

    async def _run_query(self) -> None:
        entity_type = self._selected_type()
        if entity_type is None:
            self._report_error("Select an entity type first")
            return
        table = self.query_one("#results-table", DataTable)
        table.loading = True
        try:
            if self._mode == "fts":
                query_text = self.query_one("#fts-input", Input).value.strip()
                items = await self._backend.search_entities(entity_type, query_text)
                result = PagedResult(
                    items=items, page=1, total_pages=1, total_items=len(items)
                )
            else:
                filters_input = self.query_one("#filters-input", Input)
                try:
                    filters = parse_filters(filters_input.value)
                except ValueError as exc:
                    self._report_error(str(exc))
                    return
                mode_value = self.query_one("#filter-mode-select", Select).value
                result = await self._backend.query_entities(
                    entity_type,
                    filters=filters or None,
                    filter_mode=str(mode_value),
                    page=self._current_page,
                )
        except BackendError as exc:
            self._report_error(exc.message)
            return
        finally:
            if self.is_mounted:
                table.loading = False

        self._rows = result.items
        self._total_pages = max(1, result.total_pages)
        self._render_results(result, entity_type)

    def _render_results(self, result: PagedResult, entity_type: str) -> None:
        table = self.query_one("#results-table", DataTable)
        table.clear(columns=True)
        status = self.query_one("#query-status", Label)

        if not result.items:
            status.update(f"No {entity_type} entities matched.")
            return

        sample_data = result.items[0].get("data", {})
        user_fields = list(sample_data.keys())[:_MAX_COLS]
        cols = ["id", *user_fields, "created_at"]
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

        page_part = (
            f" — page {result.page} of {result.total_pages}"
            if result.total_pages > 1
            else ""
        )
        status.update(
            f"{result.total_items} {entity_type} entities matched{page_part}."
        )

    # ------------------------------------------------------------------
    # Actions / events
    # ------------------------------------------------------------------

    async def action_next_page(self) -> None:
        if self._mode == "filters" and self._current_page < self._total_pages:
            self._current_page += 1
            self.run_query()

    async def action_prev_page(self) -> None:
        if self._mode == "filters" and self._current_page > 1:
            self._current_page -= 1
            self.run_query()

    async def action_open_detail(self) -> None:
        entity_type = self._selected_type()
        if entity_type is None:
            return
        table = self.query_one("#results-table", DataTable)
        if table.cursor_row is None or table.cursor_row >= len(self._rows):
            return
        entity_id = str(self._rows[table.cursor_row].get("id", ""))
        app = self.app
        if entity_id and hasattr(app, "open_entity_detail"):
            app.open_entity_detail(entity_type, entity_id)

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "filters-input":
            self._mode = "filters"
        elif event.input.id == "fts-input":
            self._mode = "fts"
        else:
            return
        self._current_page = 1
        self.run_query()

    async def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        entity_type = self._selected_type()
        app = self.app
        if (
            entity_type
            and event.row_key is not None
            and event.row_key.value
            and hasattr(app, "open_entity_detail")
        ):
            app.open_entity_detail(entity_type, str(event.row_key.value))
