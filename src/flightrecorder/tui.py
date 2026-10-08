"""Optional Textual terminal scrubber: pip install '.[tui]'."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, ClassVar

from textual.app import App, ComposeResult
from textual.widgets import Footer, Header, Static

from .snapshots import SnapshotIndex

if TYPE_CHECKING:
    from .boundary import Cassette


class TimelineApp(App[None]):
    TITLE = "Rewind · terminal investigation"
    BINDINGS: ClassVar = [
        ("left", "previous", "Previous"),
        ("right", "next", "Next"),
        ("q", "quit", "Quit"),
    ]
    CSS = "Screen { background: #101413; } #event { padding: 1 3; overflow-y: auto; height: 1fr; }"

    def __init__(self, cassette: Cassette) -> None:
        super().__init__()
        self.index = SnapshotIndex(cassette)
        self.position = 0

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static(id="event", markup=False)
        yield Footer()

    def on_mount(self) -> None:
        self.render_event()

    def render_event(self) -> None:
        boundaries = self.index.cassette.boundaries
        data: dict[str, Any] = (
            {"message": "No boundaries"}
            if not boundaries
            else {
                "boundary": vars(boundaries[self.position]),
                "state": self.index.at(self.position),
            }
        )
        self.query_one("#event", Static).update(json.dumps(data, indent=2, ensure_ascii=False))

    def action_previous(self) -> None:
        self.position = max(0, self.position - 1)
        self.render_event()

    def action_next(self) -> None:
        self.position = min(max(0, len(self.index.cassette.boundaries) - 1), self.position + 1)
        self.render_event()
