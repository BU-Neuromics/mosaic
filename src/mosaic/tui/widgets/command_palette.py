"""CommandPalette modal widget — fuzzy search over entity types and commands."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.message import Message
from textual.screen import ModalScreen
from textual.widgets import Input, Label, ListItem, ListView


_BUILTIN_COMMANDS = [
    "Go to schema",
    "Query",
    "Refresh",
    "Toggle theme",
    "Help",
    "Quit",
]


def _fuzzy_match(query: str, text: str) -> bool:
    """Return True if every character of *query* appears in order in *text*."""
    query = query.lower()
    text = text.lower()
    if not query:
        return True
    idx = 0
    for ch in text:
        if ch == query[idx]:
            idx += 1
            if idx == len(query):
                return True
    return False


class MosaicCommandPalette(ModalScreen):
    """A command palette modal activated by ``/`` or ``Ctrl+P``.

    Supports fuzzy-match filtering over entity type names and built-in commands.

    Args:
        entity_type_names: List of entity type names from the cached schema.
    """

    BINDINGS = [
        Binding("escape", "dismiss", "Close", show=False),
    ]

    DEFAULT_CSS = """
    MosaicCommandPalette {
        align: center middle;
    }
    MosaicCommandPalette > Vertical {
        width: 60;
        max-height: 20;
        background: $surface;
        border: round $accent;
        padding: 1;
    }
    MosaicCommandPalette Input {
        width: 100%;
        margin-bottom: 1;
    }
    MosaicCommandPalette ListView {
        height: 1fr;
    }
    """

    # ------------------------------------------------------------------
    # Messages
    # ------------------------------------------------------------------

    class EntityTypeNavigated(Message):
        """Fired when an entity type is selected from the palette."""

        def __init__(self, entity_type: str) -> None:
            super().__init__()
            self.entity_type = entity_type

    class CommandExecuted(Message):
        """Fired when a built-in command is selected."""

        def __init__(self, command: str) -> None:
            super().__init__()
            self.command = command

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def __init__(self, entity_type_names: list[str], **kwargs) -> None:
        super().__init__(**kwargs)
        self._entity_type_names = entity_type_names
        self._all_items: list[str] = entity_type_names + _BUILTIN_COMMANDS

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Input(placeholder="Type to search…", id="palette-input")
            yield ListView(id="palette-list")

    async def on_mount(self) -> None:
        await self._populate_list(self._all_items)
        self.query_one(Input).focus()

    async def _populate_list(self, items: list[str]) -> None:
        lv = self.query_one(ListView)
        await lv.clear()
        for item in items:
            await lv.append(
                ListItem(Label(item), id=f"palette-item-{item.replace(' ', '-')}")
            )

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    async def on_input_changed(self, event: Input.Changed) -> None:
        """Filter list in real time as the user types."""
        query = event.value
        matched = [item for item in self._all_items if _fuzzy_match(query, item)]
        await self._populate_list(matched)

    async def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Navigate or execute when user selects an item."""
        label = event.item.query_one(Label).renderable
        text = str(label)
        if text in _BUILTIN_COMMANDS:
            self.post_message(self.CommandExecuted(text))
        else:
            self.post_message(self.EntityTypeNavigated(text))
        self.dismiss()

    def action_dismiss(self) -> None:
        """Dismiss without action on Esc."""
        self.dismiss()
