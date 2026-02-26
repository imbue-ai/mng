import subprocess
from collections.abc import Hashable
from concurrent.futures import Future
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from datetime import timezone
from typing import Any

from loguru import logger
from pydantic import ConfigDict
from urwid.display.raw import Screen
from urwid.event_loop.abstract_loop import ExitMainLoop
from urwid.event_loop.main_loop import MainLoop
from urwid.widget.attr_map import AttrMap
from urwid.widget.columns import Columns
from urwid.widget.divider import Divider
from urwid.widget.filler import Filler
from urwid.widget.frame import Frame
from urwid.widget.listbox import ListBox
from urwid.widget.listbox import SimpleFocusListWalker
from urwid.widget.pile import Pile
from urwid.widget.text import Text
from urwid.widget.wimp import SelectableIcon

from imbue.imbue_common.mutable_model import MutableModel
from imbue.mng.config.data_types import MngContext
from imbue.mng.primitives import AgentLifecycleState
from imbue.mng.primitives import AgentName
from imbue.pankan.data_types import AgentBoardEntry
from imbue.pankan.data_types import BoardSection
from imbue.pankan.data_types import BoardSnapshot
from imbue.pankan.data_types import CheckStatus
from imbue.pankan.data_types import PrState
from imbue.pankan.fetcher import fetch_board_snapshot

REFRESH_INTERVAL_SECONDS: int = 600  # 10 minutes

SPINNER_FRAMES: tuple[str, ...] = ("|", "/", "-", "\\")
SPINNER_INTERVAL_SECONDS: float = 0.15

PALETTE = [
    ("header", "white", "dark blue"),
    ("footer", "white", "dark blue"),
    ("reversed", "standout", ""),
    # Agent states: only RUNNING and WAITING-needing-attention get color
    ("state_running", "light green", ""),
    ("state_attention", "light magenta", ""),
    # Section heading prefixes (the part before the " - ")
    ("section_done", "light magenta", ""),
    ("section_cancelled", "dark gray", ""),
    ("section_in_review", "light cyan", ""),
    ("section_drafted", "light blue", ""),
    ("section_in_progress", "yellow", ""),
    # CI checks (only failing and pending get color; passing is default)
    ("check_failing", "light red", ""),
    ("check_pending", "yellow", ""),
    ("error_text", "light red", ""),
]

# Display order: most mature first (like Linear)
BOARD_SECTION_ORDER: tuple[BoardSection, ...] = (
    BoardSection.PR_MERGED,
    BoardSection.PR_CLOSED,
    BoardSection.PR_BEING_REVIEWED,
    BoardSection.PR_DRAFTED,
    BoardSection.STILL_COOKING,
)

# Section labels split into colored prefix and plain suffix
_SECTION_PREFIX: dict[BoardSection, str] = {
    BoardSection.PR_MERGED: "Done",
    BoardSection.PR_CLOSED: "Cancelled",
    BoardSection.PR_BEING_REVIEWED: "In review",
    BoardSection.PR_DRAFTED: "Drafted",
    BoardSection.STILL_COOKING: "In progress",
}

_SECTION_SUFFIX: dict[BoardSection, str] = {
    BoardSection.PR_MERGED: "PR merged",
    BoardSection.PR_CLOSED: "PR closed",
    BoardSection.PR_BEING_REVIEWED: "PR pending",
    BoardSection.PR_DRAFTED: "PR draft",
    BoardSection.STILL_COOKING: "no PR yet",
}

_SECTION_ATTR: dict[BoardSection, str] = {
    BoardSection.PR_MERGED: "section_done",
    BoardSection.PR_CLOSED: "section_cancelled",
    BoardSection.PR_BEING_REVIEWED: "section_in_review",
    BoardSection.PR_DRAFTED: "section_drafted",
    BoardSection.STILL_COOKING: "section_in_progress",
}

_CHECK_STATUS_ATTR: dict[CheckStatus, str] = {
    CheckStatus.FAILING: "check_failing",
    CheckStatus.PENDING: "check_pending",
}


class _PankanState(MutableModel):
    """Mutable state for the pankan TUI."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    mng_ctx: MngContext
    snapshot: BoardSnapshot | None = None
    frame: Any  # urwid Frame widget
    footer_left: Any  # urwid Text widget (left side of footer)
    footer_right: Any  # urwid Text widget (right side of footer)
    loop: Any = None  # urwid MainLoop, set after construction
    spinner_index: int = 0
    refresh_future: Future[BoardSnapshot] | None = None
    executor: ThreadPoolExecutor | None = None
    # Maps list walker index -> AgentName for selectable agent entries
    index_to_agent: dict[int, AgentName] = {}
    list_walker: Any = None  # SimpleFocusListWalker, set during display build


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
            if self.state.refresh_future is None and self.state.loop is not None:
                _start_refresh(self.state.loop, self.state)
            return True
        if key in ("d", "D"):
            _delete_focused_agent(self.state)
            return True
        if key in ("up", "down", "page up", "page down", "home", "end"):
            return None
        return True


def _get_focused_agent_name(state: _PankanState) -> AgentName | None:
    """Get the agent name of the currently focused entry, or None."""
    if state.list_walker is None:
        return None
    _, focus_index = state.list_walker.get_focus()
    if focus_index is None:
        return None
    return state.index_to_agent.get(focus_index)


def _delete_focused_agent(state: _PankanState) -> None:
    """Delete the currently focused agent via mng destroy."""
    agent_name = _get_focused_agent_name(state)
    if agent_name is None:
        return

    state.footer_left.set_text(f"  Deleting {agent_name}...")

    try:
        subprocess.run(
            ["mng", "destroy", str(agent_name), "--force"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        state.footer_left.set_text(f"  Deleted {agent_name}")
    except (subprocess.TimeoutExpired, OSError) as e:
        state.footer_left.set_text(f"  Failed to delete {agent_name}: {e}")
        return

    # Trigger a refresh to update the board
    if state.refresh_future is None and state.loop is not None:
        _start_refresh(state.loop, state)


def _start_refresh(loop: MainLoop, state: _PankanState) -> None:
    """Start a background refresh and begin the spinner animation."""
    if state.executor is None:
        state.executor = ThreadPoolExecutor(max_workers=1)
    state.spinner_index = 0
    state.refresh_future = state.executor.submit(fetch_board_snapshot, state.mng_ctx)
    _schedule_spinner_tick(loop, state)


def _schedule_spinner_tick(loop: MainLoop, state: _PankanState) -> None:
    """Schedule the next spinner tick."""
    loop.set_alarm_in(SPINNER_INTERVAL_SECONDS, _on_spinner_tick, state)


def _on_spinner_tick(loop: MainLoop, state: _PankanState) -> None:
    """Alarm callback: update spinner, check if fetch is done."""
    if state.refresh_future is None:
        return

    if state.refresh_future.done():
        _finish_refresh(loop, state)
        return

    # Animate spinner
    frame_char = SPINNER_FRAMES[state.spinner_index % len(SPINNER_FRAMES)]
    state.footer_left.set_text(f"  Refreshing {frame_char}")
    state.spinner_index += 1
    _schedule_spinner_tick(loop, state)


def _finish_refresh(loop: MainLoop, state: _PankanState) -> None:
    """Complete a background refresh: update snapshot and display."""
    if state.refresh_future is None:
        return

    try:
        state.snapshot = state.refresh_future.result()
    except Exception as e:
        logger.debug("Refresh failed: {}", e)
        if state.snapshot is not None:
            state.snapshot = BoardSnapshot(
                entries=state.snapshot.entries,
                errors=(*state.snapshot.errors, f"Refresh failed: {e}"),
                fetch_time_seconds=state.snapshot.fetch_time_seconds,
            )
    finally:
        state.refresh_future = None

    _refresh_display(state)

    now = datetime.now(tz=timezone.utc).strftime("%H:%M:%S")
    if state.snapshot is not None:
        elapsed = f"{state.snapshot.fetch_time_seconds:.1f}s"
        state.footer_left.set_text(f"  Last refresh: {now} (took {elapsed})  r: refresh")
    else:
        state.footer_left.set_text(f"  Last refresh: {now}  r: refresh")

    _schedule_next_refresh(loop, state)


def _classify_entry(entry: AgentBoardEntry) -> BoardSection:
    """Determine which board section an agent belongs to based on its PR state."""
    if entry.pr is None:
        return BoardSection.STILL_COOKING
    if entry.pr.state == PrState.MERGED:
        return BoardSection.PR_MERGED
    if entry.pr.state == PrState.CLOSED:
        return BoardSection.PR_CLOSED
    if entry.pr.is_draft:
        return BoardSection.PR_DRAFTED
    return BoardSection.PR_BEING_REVIEWED


def _get_state_attr(entry: AgentBoardEntry, section: BoardSection) -> str:
    """Determine the color attribute for an agent's lifecycle state.

    Magenta is used for WAITING agents in the "still cooking" section
    (they need the user to respond). RUNNING gets green. Everything
    else is default (no color).
    """
    if entry.state == AgentLifecycleState.RUNNING:
        return "state_running"
    if entry.state == AgentLifecycleState.WAITING and section == BoardSection.STILL_COOKING:
        return "state_attention"
    return ""


def _format_check_markup(entry: AgentBoardEntry) -> str:
    """Build plain text for CI check status.

    Only failing and pending checks get color (handled at the widget level).
    Passing checks are shown in plain text. Unknown checks are not shown.
    """
    if entry.pr is None or entry.pr.check_status == CheckStatus.UNKNOWN:
        return ""
    return f"  checks {entry.pr.check_status.lower()}"


def _format_agent_text(entry: AgentBoardEntry, section: BoardSection) -> str:
    """Build plain text for a single agent line (used with SelectableIcon)."""
    state_text = f"{entry.state:<10}"
    parts = [f"  {entry.name:<24}", state_text]

    if entry.pr is not None:
        parts.append(f"  PR #{entry.pr.number}")
        parts.append(_format_check_markup(entry))
        parts.append(f"  {entry.pr.url}")

    return "".join(parts)


def _format_section_heading(section: BoardSection, count: int) -> list[str | tuple[Hashable, str]]:
    """Build urwid text markup for a section heading.

    Only the prefix (e.g. "Done") is colored; the rest is default.
    """
    prefix = _SECTION_PREFIX[section]
    suffix = _SECTION_SUFFIX[section]
    attr = _SECTION_ATTR[section]
    return [(attr, prefix), f" - {suffix} ({count})"]


def _build_board_widgets(state: _PankanState) -> SimpleFocusListWalker[AttrMap | Text | Divider]:
    """Build the urwid widget list from a BoardSnapshot, grouped by PR state.

    Returns a SimpleFocusListWalker and populates state.index_to_agent with the
    mapping from list walker index to agent name for selectable entries.
    """
    snapshot = state.snapshot
    state.index_to_agent = {}

    walker: SimpleFocusListWalker[AttrMap | Text | Divider] = SimpleFocusListWalker([])

    if snapshot is None:
        walker.append(Text("Loading..."))
        return walker

    # Classify entries into sections
    by_section: dict[BoardSection, list[AgentBoardEntry]] = {}
    for entry in snapshot.entries:
        section = _classify_entry(entry)
        by_section.setdefault(section, []).append(entry)

    has_content = False

    for section in BOARD_SECTION_ORDER:
        entries = by_section.get(section)
        if not entries:
            continue

        if has_content:
            walker.append(Divider())

        walker.append(Text(_format_section_heading(section, len(entries))))
        has_content = True

        for entry in entries:
            text = _format_agent_text(entry, section)
            item = SelectableIcon(text, cursor_position=0)
            idx = len(walker)
            walker.append(AttrMap(item, None, focus_map="reversed"))
            state.index_to_agent[idx] = entry.name

    if not has_content:
        walker.append(Text("No agents found."))

    # Show errors if any
    if snapshot.errors:
        walker.append(Divider())
        walker.append(Text(("error_text", "Errors:")))
        for error in snapshot.errors:
            walker.append(Text(("error_text", f"  {error}")))

    return walker


def _refresh_display(state: _PankanState) -> None:
    """Rebuild the body display from the current snapshot."""
    walker = _build_board_widgets(state)
    state.list_walker = walker
    state.frame.body = ListBox(walker)


def _schedule_next_refresh(loop: MainLoop, state: _PankanState) -> None:
    """Schedule the next auto-refresh alarm."""
    loop.set_alarm_in(REFRESH_INTERVAL_SECONDS, _on_auto_refresh_alarm, state)


def _on_auto_refresh_alarm(loop: MainLoop, state: _PankanState) -> None:
    """Alarm callback for periodic auto-refresh."""
    if state.refresh_future is None:
        _start_refresh(loop, state)


def run_pankan(mng_ctx: MngContext) -> None:
    """Run the pankan TUI board."""
    footer_left = Text("  Loading...")
    footer_right = Text("d: delete  q: quit  ", align="right")
    pack: int = len("d: delete  q: quit  ")
    footer_columns = Columns([footer_left, (pack, footer_right)])
    footer = Pile([Divider(), AttrMap(footer_columns, "footer")])

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
        footer_left=footer_left,
        footer_right=footer_right,
    )

    input_handler = _PankanInputHandler(state=state)

    screen = Screen()
    screen.tty_signal_keys(intr="undefined")

    loop = MainLoop(frame, palette=PALETTE, unhandled_input=input_handler, screen=screen)
    state.loop = loop

    # Initial data load with spinner
    _start_refresh(loop, state)

    logger.disable("imbue")
    try:
        loop.run()
    finally:
        logger.enable("imbue")
        if state.executor is not None:
            state.executor.shutdown(wait=False)
