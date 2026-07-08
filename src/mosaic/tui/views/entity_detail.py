"""EntityDetailScreen — full entity detail with relationships and provenance."""

from __future__ import annotations

from typing import Any

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import DataTable, Footer, Label, ListItem, ListView, Static

from mosaic.tui.backend.protocol import (
    SYSTEM_FIELDS,
    BackendError,
    EntityDetail,
    ProvenanceEvent,
    TUIBackend,
)
from mosaic.tui.render import format_timestamp, format_value, short_id

#: How many provenance events the detail screen previews.
_PROVENANCE_PREVIEW = 5


class EntityDetailScreen(Screen):
    """Detail screen for a single entity.

    Shows every field (system + temporal fields first, then user slots),
    outbound relationships (Enter follows the link), and a provenance
    preview. The screen fetches its own data so it can refresh and so
    relationship navigation can chain detail screens.

    Args:
        backend: The TUIBackend to fetch data from.
        entity_type: The entity's type.
        entity_id: The entity's id.
    """

    DEFAULT_CSS = """
    EntityDetailScreen #detail-title {
        height: 1;
        padding: 0 1;
        text-style: bold;
        color: $text-accent;
    }
    EntityDetailScreen #detail-columns {
        height: 1fr;
    }
    EntityDetailScreen #fields-panel {
        width: 3fr;
        border-right: solid $panel;
    }
    EntityDetailScreen #right-panel {
        width: 2fr;
    }
    EntityDetailScreen .panel-header {
        height: 1;
        padding: 0 1;
        color: $text-muted;
        text-style: bold;
    }
    EntityDetailScreen #fields-table {
        height: 1fr;
    }
    EntityDetailScreen #rel-list {
        height: 2fr;
    }
    EntityDetailScreen #prov-list {
        height: 2fr;
    }
    EntityDetailScreen .empty-note {
        padding: 0 1;
        color: $text-muted;
    }
    """

    BINDINGS = [
        Binding("escape", "go_back", "Back", show=True),
        Binding("e", "edit_entity", "Edit", show=True),
        Binding("a", "availability", "Availability", show=True),
        Binding("p", "provenance", "Provenance", show=True),
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
        self._entity: EntityDetail | None = None
        self._provenance: list[ProvenanceEvent] = []

    def compose(self) -> ComposeResult:
        yield Label(
            f"{self._entity_type}: {self._entity_id}", id="detail-title"
        )
        with Horizontal(id="detail-columns"):
            with Vertical(id="fields-panel"):
                yield Label("Fields", classes="panel-header")
                yield DataTable(id="fields-table", cursor_type="row")
            with Vertical(id="right-panel"):
                yield Label("Relationships (Enter follows)", classes="panel-header")
                yield ListView(id="rel-list")
                yield Label(
                    f"Provenance (last {_PROVENANCE_PREVIEW} — p for full history)",
                    classes="panel-header",
                )
                yield ListView(id="prov-list")
        yield Footer()

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
        """Reload the entity and its provenance in a background worker."""
        self.run_worker(self._load(), exclusive=True, group="detail-load")

    async def _load(self) -> None:
        if not self.is_mounted:
            return
        table = self.query_one("#fields-table", DataTable)
        table.loading = True
        try:
            self._entity = await self._backend.get_entity(
                self._entity_type, self._entity_id
            )
            self._provenance = await self._backend.get_provenance(
                self._entity_type, self._entity_id
            )
        except BackendError as exc:
            self._report_error(exc.message)
            return
        finally:
            if self.is_mounted:
                table.loading = False
        await self._render_detail()

    async def _render_detail(self) -> None:
        entity = self._entity
        if entity is None:
            return

        # Fields table — system fields first (dimmed), then user slots.
        table = self.query_one("#fields-table", DataTable)
        table.clear(columns=True)
        table.add_column("Field", key="field", width=24)
        table.add_column("Value", key="value")
        system_names = set(SYSTEM_FIELDS)
        for name, value in entity.fields.items():
            rendered = format_value(value, max_len=200)
            if name in system_names:
                table.add_row(f"[dim]{name}[/dim]", f"[dim]{rendered}[/dim]")
            else:
                table.add_row(name, rendered)

        # Relationships
        rel_list = self.query_one("#rel-list", ListView)
        await rel_list.clear()
        if entity.relationships:
            for index, rel in enumerate(entity.relationships):
                item = ListItem(
                    Label(
                        f"{rel.relationship_name} → {rel.target_type} "
                        f"{short_id(rel.target_id)}"
                    ),
                    id=f"rel-{index}",
                )
                await rel_list.append(item)
        else:
            await rel_list.append(
                ListItem(Static("(none)", classes="empty-note"), disabled=True)
            )

        # Provenance preview (newest first)
        prov_list = self.query_one("#prov-list", ListView)
        await prov_list.clear()
        if self._provenance:
            for event in self._provenance[:_PROVENANCE_PREVIEW]:
                actor = f"  by {event.actor}" if event.actor else ""
                await prov_list.append(
                    ListItem(
                        Label(
                            f"● {event.event_type:<10} "
                            f"{format_timestamp(event.timestamp)}{actor}"
                        ),
                        disabled=True,
                    )
                )
        else:
            await prov_list.append(
                ListItem(Static("(no provenance)", classes="empty-note"), disabled=True)
            )

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def action_go_back(self) -> None:
        self.app.pop_screen()

    async def action_refresh(self) -> None:
        self.reload()

    async def action_edit_entity(self) -> None:
        """Open the edit form for this entity."""
        from mosaic.tui.views.entity_form import EntityFormScreen

        if self._entity is None:
            return
        app = self.app
        try:
            if hasattr(app, "get_or_fetch_schema"):
                schema = await app.get_or_fetch_schema()
            else:
                schema = await self._backend.get_schema()
        except BackendError as exc:
            self._report_error(exc.message)
            return
        entity_schema = schema.get_entity_type(self._entity_type)
        if entity_schema is None:
            self._report_error(f"No schema available for {self._entity_type}")
            return

        def on_saved(saved_id: str | None) -> None:
            if saved_id:
                self.notify(f"Updated {self._entity_type} {short_id(saved_id)}")
                self.reload()

        await app.push_screen(
            EntityFormScreen(
                backend=self._backend,
                entity_type=self._entity_type,
                entity_schema=entity_schema,
                entity_id=self._entity_id,
                initial=self._entity.data,
            ),
            on_saved,
        )

    async def action_availability(self) -> None:
        """Open the availability transition dialog for this entity."""
        from mosaic.tui.widgets.availability_dialog import AvailabilityScreen

        async def on_result(result: tuple[bool, str] | None) -> None:
            if result is None:
                return
            is_available, reason = result
            try:
                await self._backend.set_availability(
                    self._entity_type, self._entity_id, is_available, reason
                )
            except BackendError as exc:
                self._report_error(exc.message)
                return
            self.notify(f"Availability updated: {reason}")
            self.reload()

        await self.app.push_screen(
            AvailabilityScreen(entity_label=short_id(self._entity_id, 12)),
            on_result,
        )

    async def action_provenance(self) -> None:
        """Open the full provenance history screen."""
        from mosaic.tui.views.provenance import ProvenanceScreen

        await self.app.push_screen(
            ProvenanceScreen(
                backend=self._backend,
                entity_type=self._entity_type,
                entity_id=self._entity_id,
            )
        )

    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------

    async def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Follow a relationship link to the target entity's detail."""
        if event.list_view.id != "rel-list" or self._entity is None:
            return
        item_id = event.item.id or ""
        if not item_id.startswith("rel-"):
            return
        index = int(item_id.removeprefix("rel-"))
        if index >= len(self._entity.relationships):
            return
        rel = self._entity.relationships[index]
        app = self.app
        if hasattr(app, "open_entity_detail"):
            app.open_entity_detail(rel.target_type, rel.target_id)
