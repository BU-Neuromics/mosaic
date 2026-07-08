"""SchemaExplorerView — entity types, slots, and navigable relationships."""

from __future__ import annotations

from typing import Any

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widget import Widget
from textual.widgets import DataTable, Label, ListItem, ListView

from mosaic.tui.backend.protocol import EntityTypeSchema, SchemaView


class SchemaExplorerView(Widget):
    """Schema explorer: entity type list, slot table, and relationship graph.

    Relationships are navigable — selecting one jumps to its target type,
    so the graph-shaped schema can be walked from the keyboard.

    Args:
        schema: Cached ``SchemaView`` from ``MosaicTUIApp``.
        app_ref: Reference to the parent ``MosaicTUIApp`` for cache invalidation.
    """

    DEFAULT_CSS = """
    SchemaExplorerView {
        height: 1fr;
    }
    SchemaExplorerView #schema-left {
        width: 30;
        border-right: solid $panel;
    }
    SchemaExplorerView #schema-right {
        width: 1fr;
    }
    SchemaExplorerView .panel-header {
        height: 1;
        padding: 0 1;
        color: $text-muted;
        text-style: bold;
    }
    SchemaExplorerView #type-description {
        height: auto;
        max-height: 3;
        padding: 0 1;
        color: $text-muted;
    }
    SchemaExplorerView #field-table {
        height: 2fr;
    }
    SchemaExplorerView #rel-list {
        height: 1fr;
    }
    """

    BINDINGS = [
        Binding("r", "refresh_schema", "Refresh", show=True),
    ]

    def __init__(self, schema: SchemaView, app_ref: Any = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._schema = schema
        self._app_ref = app_ref
        self._selected_type: str | None = None

    def compose(self) -> ComposeResult:
        with Horizontal(id="schema-main"):
            with Vertical(id="schema-left"):
                yield Label("Entity Types", classes="panel-header")
                yield ListView(id="entity-type-list")
            with Vertical(id="schema-right"):
                yield Label("Fields", id="schema-right-header", classes="panel-header")
                yield Label("", id="type-description")
                yield DataTable(id="field-table", cursor_type="row")
                yield Label(
                    "Relationships (Enter jumps to target type)",
                    id="rel-section-header",
                    classes="panel-header",
                )
                yield ListView(id="rel-list")

    async def on_mount(self) -> None:
        """Populate the entity type list on mount."""
        await self._populate_entity_list()
        if self._schema.entity_types:
            await self._show_entity_type(self._schema.entity_types[0])

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _populate_entity_list(self) -> None:
        lv = self.query_one("#entity-type-list", ListView)
        await lv.clear()
        for et in self._schema.entity_types:
            field_count = len(et.fields)
            await lv.append(
                ListItem(
                    Label(f"{et.name}   [dim]{field_count} fields[/dim]"),
                    id=f"et-{et.name}",
                )
            )

    async def _show_entity_type(self, entity_schema: EntityTypeSchema) -> None:
        """Populate the right panel with fields for *entity_schema*."""
        if not self.is_mounted:
            self._selected_type = entity_schema.name
            return
        self._selected_type = entity_schema.name
        try:
            header = self.query_one("#schema-right-header", Label)
            header.update(f"Fields: {entity_schema.name}")
            description = self.query_one("#type-description", Label)
            description.update(entity_schema.description or "")
        except Exception:  # noqa: BLE001 — partial mount
            pass

        # Rebuild field table
        table = self.query_one("#field-table", DataTable)
        table.clear(columns=True)
        table.add_column("Field", key="field", width=22)
        table.add_column("Type", key="type", width=20)
        table.add_column("Req", key="req", width=5)
        table.add_column("Idx", key="idx", width=5)
        table.add_column("Multi", key="multi", width=7)
        table.add_column("Enum values / description", key="extra")

        for field in entity_schema.fields:
            field_type = field.field_type
            if field.ref_target:
                field_type = f"ref → {field.ref_target}"
            extra = ""
            if field.enum_values:
                extra = ", ".join(field.enum_values)
            elif field.description:
                extra = field.description
            table.add_row(
                field.name,
                field_type,
                "✓" if field.required else "-",
                "✓" if field.indexed else "-",
                "✓" if field.multivalued else "-",
                extra,
            )

        await self._populate_relationships()

    async def _populate_relationships(self) -> None:
        lv = self.query_one("#rel-list", ListView)
        await lv.clear()

        relationships = [
            rel
            for rel in self._schema.relationships
            if rel.source_type == self._selected_type
            or rel.target_type == self._selected_type
        ] or self._schema.relationships

        if not relationships:
            await lv.append(
                ListItem(Label("(no relationships defined)"), disabled=True)
            )
            return

        for index, rel in enumerate(relationships):
            text = (
                f"{rel.source_type} ──{rel.relationship_name}──▶ {rel.target_type}"
            )
            item = ListItem(Label(text), id=f"schema-rel-{index}")
            item._rel_target = rel.target_type  # type: ignore[attr-defined]
            await lv.append(item)

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    async def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Entity type selection updates the field table; relationship
        selection jumps to the relationship's target type."""
        item = event.item
        if event.list_view.id == "entity-type-list":
            et_name = item.id.removeprefix("et-") if item.id else None
            if et_name:
                et = self._schema.get_entity_type(et_name)
                if et is not None:
                    await self._show_entity_type(et)
        elif event.list_view.id == "rel-list":
            target = getattr(item, "_rel_target", None)
            if target:
                et = self._schema.get_entity_type(target)
                if et is not None:
                    await self._show_entity_type(et)
                    self._highlight_type_in_list(target)

    def _highlight_type_in_list(self, name: str) -> None:
        try:
            lv = self.query_one("#entity-type-list", ListView)
            for index, item in enumerate(lv.query(ListItem)):
                if item.id == f"et-{name}":
                    lv.index = index
                    break
        except Exception:  # noqa: BLE001 — not mounted
            pass

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    async def action_refresh_schema(self) -> None:
        """Invalidate schema cache, re-fetch, and re-render."""
        if self._app_ref is not None:
            self._schema = await self._app_ref.invalidate_schema_cache()
        if not self.is_mounted:
            return
        await self._populate_entity_list()
        if self._schema.entity_types:
            await self._show_entity_type(self._schema.entity_types[0])
