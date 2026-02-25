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
from imbue.mng_pankan.data_types import AgentBoardEntry
from imbue.mng_pankan.data_types import BoardSnapshot
from imbue.mng_pankan.data_types import CheckStatus
from imbue.mng_pankan.data_types import PrState
from imbue.mng_pankan.fetcher import fetch_board_snapshot

REFRESH_INTERVAL_SECONDS: int = 600  # 10 minutes

PALETTE = [
    ("header", "white", "dark blue"),
    ("footer", "white", "dark blue"),
    ("state_running", "light green", ""),
    ("state_waiting", "yellow", ""),
    ("state_stopped", "light red", ""),
    ("state_done", "dark gray", ""),
    ("state_replaced", "dark gray", ""),
    ("pr_open", "light green", ""),
    ("pr_merged", "light magenta", ""),
    ("pr_closed", "light red", ""),
    ("check_passing", "light green", ""),
    ("check_failing", "light red", ""),
    ("check_pending", "yellow", ""),
    ("check_unknown", "dark gray", ""),
    ("section_heading", "bold", ""),
    ("no_pr", "dark gray", ""),
    ("error_text", "light red", ""),
]

# Display order for lifecycle states
LIFECYCLE_STATE_ORDER: tuple[AgentLifecycleState, ...] = (
    AgentLifecycleState.RUNNING,
    AgentLifecycleState.WAITING,
    AgentLifecycleState.STOPPED,
    AgentLifecycleState.DONE,
    AgentLifecycleState.REPLACED,
)

_STATE_ATTR: dict[AgentLifecycleState, str] = {
    AgentLifecycleState.RUNNING: "state_running",
    AgentLifecycleState.WAITING: "state_waiting",
    AgentLifecycleState.STOPPED: "state_stopped",
    AgentLifecycleState.DONE: "state_done",
    AgentLifecycleState.REPLACED: "state_replaced",
}

_PR_STATE_ATTR: dict[PrState, str] = {
    PrState.OPEN: "pr_open",
    PrState.CLOSED: "pr_closed",
    PrState.MERGED: "pr_merged",
}

_CHECK_STATUS_ATTR: dict[CheckStatus, str] = {
    CheckStatus.PASSING: "check_passing",
    CheckStatus.FAILING: "check_failing",
    CheckStatus.PENDING: "check_pending",
    CheckStatus.UNKNOWN: "check_unknown",
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


def _format_pr_markup(entry: AgentBoardEntry) -> list[str | tuple[Hashable, str]]:
    """Build urwid text markup for an agent's PR info."""
    if entry.pr is None:
        return [("no_pr", "(no PR)")]

    pr = entry.pr
    pr_state_attr = _PR_STATE_ATTR[pr.state]
    check_attr = _CHECK_STATUS_ATTR[pr.check_status]

    parts: list[str | tuple[Hashable, str]] = [
        f"PR #{pr.number} ",
        (pr_state_attr, pr.state.lower()),
    ]

    if pr.check_status != CheckStatus.UNKNOWN:
        parts.append("  checks ")
        parts.append((check_attr, pr.check_status.lower()))

    return parts


def _format_agent_line(entry: AgentBoardEntry) -> list[str | tuple[Hashable, str]]:
    """Build urwid text markup for a single agent line."""
    state_attr = _STATE_ATTR.get(entry.state, "")
    name_padded = f"  {entry.name:<24}"
    parts: list[str | tuple[Hashable, str]] = [
        (state_attr, name_padded),
    ]
    parts.extend(_format_pr_markup(entry))
    return parts


def _build_board_widgets(snapshot: BoardSnapshot) -> list[Text | Divider]:
    """Build the urwid widget list from a BoardSnapshot, grouped by lifecycle state."""
    # Group entries by state
    by_state: dict[AgentLifecycleState, list[AgentBoardEntry]] = {}
    for entry in snapshot.entries:
        by_state.setdefault(entry.state, []).append(entry)

    widgets: list[Text | Divider] = []

    for state in LIFECYCLE_STATE_ORDER:
        entries = by_state.get(state)
        if not entries:
            continue

        if widgets:
            widgets.append(Divider())

        # Section heading
        state_attr = _STATE_ATTR.get(state, "")
        heading = f"{state} ({len(entries)})"
        widgets.append(Text((state_attr, heading)))

        for entry in entries:
            widgets.append(Text(_format_agent_line(entry)))

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
