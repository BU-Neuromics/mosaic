"""HelpOverlay — modal showing all keyboard shortcuts."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import DataTable, Label


_SHORTCUTS: list[tuple[str, str]] = [
    ("q / Ctrl+C", "Quit"),
    ("?", "Show this help overlay"),
    ("/ or Ctrl+P", "Open command palette"),
    ("Ctrl+Q", "Open query view"),
    ("Ctrl+T", "Toggle dark/light theme"),
    ("Tab", "Cycle focus between panels"),
    ("↑ / ↓", "Navigate lists"),
    ("Enter", "Select / drill in"),
    ("Esc", "Go back / dismiss"),
    ("r", "Refresh current view"),
    ("f", "Focus filter bar (Entity Browser)"),
    ("← / →", "Previous / next page (Entity Browser)"),
    ("n", "New entity (Entity Browser)"),
    ("e", "Edit entity (browser / detail)"),
    ("a", "Change availability (browser / detail)"),
    ("p", "Provenance history (browser / detail)"),
]


class HelpOverlay(ModalScreen):
    """A modal overlay that lists all global keyboard shortcuts.

    Dismiss with ``Esc``.
    """

    BINDINGS = [
        Binding("escape", "dismiss", "Close", show=False),
    ]

    DEFAULT_CSS = """
    HelpOverlay {
        align: center middle;
    }
    HelpOverlay > Vertical {
        width: 60;
        height: auto;
        max-height: 28;
        background: $surface;
        border: round $accent;
        padding: 1;
    }
    HelpOverlay Label#help-title {
        text-style: bold;
        margin-bottom: 1;
        width: 100%;
        text-align: center;
    }
    HelpOverlay DataTable {
        height: auto;
    }
    """

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label("Keyboard Shortcuts", id="help-title")
            table = DataTable(id="shortcut-table", show_header=True)
            yield table

    def on_mount(self) -> None:
        table = self.query_one(DataTable)
        table.add_column("Key", width=20)
        table.add_column("Action", width=36)
        for key, description in _SHORTCUTS:
            table.add_row(key, description)

    def action_dismiss(self) -> None:
        """Dismiss the overlay on Esc."""
        self.dismiss()
