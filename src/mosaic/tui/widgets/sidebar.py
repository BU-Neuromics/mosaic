"""EntityTypeSidebar widget — entity types plus Query and Schema Explorer entries."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.message import Message
from textual.widgets import Label, ListItem, ListView

from mosaic.tui.backend.protocol import TUIBackend

_SCHEMA_EXPLORER_LABEL = "Schema Explorer"
_QUERY_LABEL = "Query"


class EntityTypeSidebar(ListView):
    """A ``ListView`` sidebar listing entity types and navigation entries.

    Emits:
        EntityTypeSelected — when the user selects an entity type.
        QuerySelected — when the user selects the Query entry.
        SchemaExplorerSelected — when the user selects the Schema Explorer entry.
    """

    DEFAULT_CSS = """
    EntityTypeSidebar > ListItem.section-entry Label {
        color: $text-accent;
    }
    """

    # ------------------------------------------------------------------
    # Messages
    # ------------------------------------------------------------------

    class EntityTypeSelected(Message):
        """Fired when an entity type is selected."""

        def __init__(self, entity_type: str, entity_count: int = 0) -> None:
            super().__init__()
            self.entity_type = entity_type
            self.entity_count = entity_count

    class QuerySelected(Message):
        """Fired when the Query entry is selected."""

    class SchemaExplorerSelected(Message):
        """Fired when the Schema Explorer entry is selected."""

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def compose(self) -> ComposeResult:
        # Entity type items are populated dynamically via load_entity_types()
        yield ListItem(
            Label(_QUERY_LABEL), id="query-item", classes="section-entry"
        )
        yield ListItem(
            Label(_SCHEMA_EXPLORER_LABEL),
            id="schema-explorer-item",
            classes="section-entry",
        )

    async def load_entity_types(self, backend: TUIBackend) -> None:
        """Fetch entity types from *backend* and populate the list.

        The Query and Schema Explorer entries always stay at the bottom.
        Backend failures leave the navigation entries intact and re-raise
        as :class:`BackendError` for the app to report.
        """
        summaries = await backend.list_entity_types()

        # Remove all existing entity type items
        for item in list(self.query(ListItem)):
            if item.id not in ("schema-explorer-item", "query-item"):
                await item.remove()

        # Insert entity type items before the Query entry
        anchor = self.query_one("#query-item")
        for summary in summaries:
            label_text = f"{summary.name}  ({summary.count})"
            new_item = ListItem(
                Label(label_text),
                id=f"entity-type-{summary.name}",
            )
            # Store metadata for selection handling
            new_item._entity_type = summary.name  # type: ignore[attr-defined]
            new_item._entity_count = summary.count  # type: ignore[attr-defined]
            await self.mount(new_item, before=anchor)

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Determine which item was selected and emit the right message."""
        item = event.item
        if item.id == "schema-explorer-item":
            self.post_message(self.SchemaExplorerSelected())
        elif item.id == "query-item":
            self.post_message(self.QuerySelected())
        elif item.id and item.id.startswith("entity-type-"):
            entity_type = getattr(
                item, "_entity_type", item.id.removeprefix("entity-type-")
            )
            entity_count = getattr(item, "_entity_count", 0)
            self.post_message(self.EntityTypeSelected(entity_type, entity_count))
