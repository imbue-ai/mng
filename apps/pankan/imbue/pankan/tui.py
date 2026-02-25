from collections.abc import Hashable
from datetime import datetime
from datetime import timezone
from typing import Any

from loguru import logger
from pydantic import ConfigDict
from urwid.display.raw import Screen
from urwid.event_loop.abstract_loop import ExitMainLoop
from urwid.event_loop.main_loop import MainLoop
from urwid.widget.attr_map import AttrMap
from urwid.widget.divider import Divider
from urwid.widget.filler import Filler
from urwid.widget.frame import Frame
from urwid.widget.listbox import ListBox
from urwid.widget.listbox import SimpleFocusListWalker
from urwid.widget.pile import Pile
from urwid.widget.text import Text

from imbue.imbue_common.mutable_model import MutableModel
from imbue.mng.config.data_types import MngContext
from imbue.mng.primitives import AgentLifecycleState
from imbue.pankan.data_types import AgentBoardEntry
from imbue.pankan.data_types import BoardSection
from imbue.pankan.data_types import BoardSnapshot
from imbue.pankan.data_types import CheckStatus
from imbue.pankan.data_types import PrState
from imbue.pankan.fetcher import fetch_board_snapshot

REFRESH_INTERVAL_SECONDS: int = 600  # 10 minutes

PALETTE = [
    ("header", "white", "dark blue"),
    ("footer", "white", "dark blue"),
    # Agent states: only RUNNING and WAITING-needing-attention get color
    ("state_running", "light green", ""),
    ("state_attention", "light red", ""),
    # Section headings
    ("section_done", "light magenta", ""),
    ("section_cancelled", "dark gray", ""),
    ("section_in_review", "light cyan", ""),
    ("section_in_progress", "yellow", ""),
    # CI checks
    ("check_passing", "light green", ""),
    ("check_failing", "light red", ""),
    ("check_pending", "yellow", ""),
    ("error_text", "light red", ""),
]

# Display order: most mature first (like Linear)
BOARD_SECTION_ORDER: tuple[BoardSection, ...] = (
    BoardSection.PR_MERGED,
    BoardSection.PR_CLOSED,
    BoardSection.PR_BEING_REVIEWED,
    BoardSection.STILL_COOKING,
)

_SECTION_LABELS: dict[BoardSection, str] = {
    BoardSection.PR_MERGED: "Done - PR merged",
    BoardSection.PR_CLOSED: "Cancelled - PR closed",
    BoardSection.PR_BEING_REVIEWED: "In review - PR pending",
    BoardSection.STILL_COOKING: "In progress - still cooking locally",
}

_SECTION_ATTR: dict[BoardSection, str] = {
    BoardSection.PR_MERGED: "section_done",
    BoardSection.PR_CLOSED: "section_cancelled",
    BoardSection.PR_BEING_REVIEWED: "section_in_review",
    BoardSection.STILL_COOKING: "section_in_progress",
}

_CHECK_STATUS_ATTR: dict[CheckStatus, str] = {
    CheckStatus.PASSING: "check_passing",
    CheckStatus.FAILING: "check_failing",
    CheckStatus.PENDING: "check_pending",
}


class _PankanState(MutableModel):
    """Mutable state for the pankan TUI."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    mng_ctx: MngContext
    snapshot: BoardSnapshot | None = None
    frame: Any  # urwid Frame widget
    footer_text: Any  # urwid Text widget
    loop: Any = None  # urwid MainLoop, set after construction


class _PankanInputHandler(MutableModel):
    """Callable input handler for the pankan TUI."""

    state: _PankanState

    def __call__(self, key: str | tuple[str, int, int, int]) -> bool | None:
        """Handle keyboard input. Returns True if handled, None to pass through."""
        if isinstance(key, tuple):
            return None
        if key in ("q", "Q", "ctrl c"):
            raise ExitMainLoop()
        if key in ("r", "R"):
            self.state.footer_text.set_text("  Refreshing...")
            # Defer refresh to next event loop iteration so the draw happens first
            if self.state.loop is not None:
                self.state.loop.set_alarm_in(0, _on_refresh_alarm, self.state)
            return True
        if key in ("up", "down", "page up", "page down", "home", "end"):
            return None
        return True


def _classify_entry(entry: AgentBoardEntry) -> BoardSection:
    """Determine which board section an agent belongs to based on its PR state."""
    if entry.pr is None:
        return BoardSection.STILL_COOKING
    if entry.pr.state == PrState.MERGED:
        return BoardSection.PR_MERGED
    if entry.pr.state == PrState.CLOSED:
        return BoardSection.PR_CLOSED
    return BoardSection.PR_BEING_REVIEWED


def _get_state_attr(entry: AgentBoardEntry, section: BoardSection) -> str:
    """Determine the color attribute for an agent's lifecycle state.

    Red is reserved for states that require user attention:
    - WAITING agents in the "still cooking" section need the user to respond
    - CI check failures also use red (handled separately)

    RUNNING gets green. Everything else is default (no color).
    """
    if entry.state == AgentLifecycleState.RUNNING:
        return "state_running"
    if entry.state == AgentLifecycleState.WAITING and section == BoardSection.STILL_COOKING:
        return "state_attention"
    return ""


def _format_check_markup(entry: AgentBoardEntry) -> list[str | tuple[Hashable, str]]:
    """Build urwid text markup for CI check status."""
    if entry.pr is None or entry.pr.check_status == CheckStatus.UNKNOWN:
        return []
    check_attr = _CHECK_STATUS_ATTR.get(entry.pr.check_status, "")
    if not check_attr:
        return []
    return ["  checks ", (check_attr, entry.pr.check_status.lower())]


def _format_agent_line(entry: AgentBoardEntry, section: BoardSection) -> list[str | tuple[Hashable, str]]:
    """Build urwid text markup for a single agent line.

    Shows: name, agent state, PR info (number + checks if applicable).
    """
    state_attr = _get_state_attr(entry, section)
    state_text = f"{entry.state:<10}"
    parts: list[str | tuple[Hashable, str]] = [
        f"  {entry.name:<24}",
    ]
    if state_attr:
        parts.append((state_attr, state_text))
    else:
        parts.append(state_text)

    if entry.pr is not None:
        parts.append(f"  PR #{entry.pr.number}")
        parts.extend(_format_check_markup(entry))

    return parts


def _build_board_widgets(snapshot: BoardSnapshot) -> list[Text | Divider]:
    """Build the urwid widget list from a BoardSnapshot, grouped by PR state."""
    # Classify entries into sections
    by_section: dict[BoardSection, list[AgentBoardEntry]] = {}
    for entry in snapshot.entries:
        section = _classify_entry(entry)
        by_section.setdefault(section, []).append(entry)

    widgets: list[Text | Divider] = []

    for section in BOARD_SECTION_ORDER:
        entries = by_section.get(section)
        if not entries:
            continue

        if widgets:
            widgets.append(Divider())

        # Section heading
        section_attr = _SECTION_ATTR[section]
        label = _SECTION_LABELS[section]
        heading = f"{label} ({len(entries)})"
        widgets.append(Text((section_attr, heading)))

        for entry in entries:
            widgets.append(Text(_format_agent_line(entry, section)))

    if not widgets:
        widgets.append(Text("No agents found."))

    # Show errors if any
    if snapshot.errors:
        widgets.append(Divider())
        widgets.append(Text(("error_text", "Errors:")))
        for error in snapshot.errors:
            widgets.append(Text(("error_text", f"  {error}")))

    return widgets


def _refresh_display(state: _PankanState) -> None:
    """Rebuild the body display from the current snapshot."""
    if state.snapshot is None:
        body = Filler(Pile([Text("Loading...")]), valign="top")
    else:
        widgets = _build_board_widgets(state.snapshot)
        body = ListBox(SimpleFocusListWalker(widgets))

    state.frame.body = body


def _do_refresh(state: _PankanState) -> None:
    """Fetch new data and update the display."""
    state.snapshot = fetch_board_snapshot(state.mng_ctx)
    _refresh_display(state)

    now = datetime.now(tz=timezone.utc).strftime("%H:%M:%S")
    elapsed = f"{state.snapshot.fetch_time_seconds:.1f}s"
    state.footer_text.set_text(f"  Last refresh: {now} ({elapsed}) | r: refresh | q: quit")


def _on_refresh_alarm(loop: MainLoop, state: _PankanState) -> None:
    """Alarm callback for periodic and manual refresh."""
    _do_refresh(state)
    _schedule_next_refresh(loop, state)


def _schedule_next_refresh(loop: MainLoop, state: _PankanState) -> None:
    """Schedule the next auto-refresh alarm."""
    loop.set_alarm_in(REFRESH_INTERVAL_SECONDS, _on_refresh_alarm, state)


def run_pankan(mng_ctx: MngContext) -> None:
    """Run the pankan TUI board."""
    footer_text = Text("  Loading...")
    footer = Pile([Divider(), AttrMap(footer_text, "footer")])

    header = Pile(
        [
            AttrMap(Text("pankan - Agent Work Tracker", align="center"), "header"),
            Divider(),
        ]
    )

    initial_body = Filler(Pile([Text("Loading...")]), valign="top")
    frame = Frame(body=initial_body, header=header, footer=footer)

    state = _PankanState(
        mng_ctx=mng_ctx,
        frame=frame,
        footer_text=footer_text,
    )

    input_handler = _PankanInputHandler(state=state)

    screen = Screen()
    screen.tty_signal_keys(intr="undefined")

    loop = MainLoop(frame, palette=PALETTE, unhandled_input=input_handler, screen=screen)
    state.loop = loop

    # Initial data load + schedule periodic refresh
    loop.set_alarm_in(0, _on_refresh_alarm, state)

    logger.disable("imbue")
    try:
        loop.run()
    finally:
        logger.enable("imbue")
