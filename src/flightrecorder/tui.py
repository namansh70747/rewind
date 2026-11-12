"""Optional Textual terminal scrubber: pip install '.[tui]'."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, ClassVar

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.widgets import Footer, Header, Static

from .snapshots import SnapshotIndex

if TYPE_CHECKING:
    from .boundary import Cassette


class TimelineApp(App[None]):
    TITLE = "Rewind · terminal investigation"
    BINDINGS: ClassVar = [
        Binding("left", "previous", "Previous", priority=True),
        Binding("right", "next", "Next", priority=True),
        Binding("home", "first", "First", priority=True),
        Binding("end", "last", "Last", priority=True),
        ("q", "quit", "Quit"),
    ]
    CSS = """
    Screen { background: #101413; }
    #summary { height: auto; padding: 1 3; color: #9dd6bd; }
    #details { height: 1fr; padding: 0 3; }
    #event { height: auto; }
    """

    def __init__(self, cassette: Cassette) -> None:
        super().__init__()
        self.index = SnapshotIndex(cassette)
        self.position = 0
        if cassette.metadata.get("counterfactual"):
            self.title = "Rewind · QUARANTINED what-if · best-effort exploration"

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static(id="summary", markup=False)
        with VerticalScroll(id="details"):
            yield Static(id="event", markup=False)
        yield Footer()

    def on_mount(self) -> None:
        self.render_event()
        self.query_one("#details", VerticalScroll).focus()

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
        summary = "Empty recording"
        if boundaries:
            boundary = boundaries[self.position]
            summary = (
                f"Boundary {self.position}/{len(boundaries) - 1}  {boundary.kind}/{boundary.key}\n"
                f"Chain: {boundary.chain_hash}"
            )
        self.query_one("#summary", Static).update(summary)
        self.query_one("#details", VerticalScroll).scroll_home(animate=False)
        self.query_one("#event", Static).update(json.dumps(data, indent=2, ensure_ascii=False))

    def action_previous(self) -> None:
        self.position = max(0, self.position - 1)
        self.render_event()

    def action_next(self) -> None:
        self.position = min(max(0, len(self.index.cassette.boundaries) - 1), self.position + 1)
        self.render_event()

    def action_first(self) -> None:
        self.position = 0
        self.render_event()

    def action_last(self) -> None:
        self.position = max(0, len(self.index.cassette.boundaries) - 1)
        self.render_event()
