"""Unit tests for the kanpan TUI."""

import subprocess
from concurrent.futures import Future
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from urwid.event_loop.abstract_loop import ExitMainLoop
from urwid.widget.attr_map import AttrMap
from urwid.widget.text import Text

from imbue.mng.primitives import AgentLifecycleState
from imbue.mng.primitives import AgentName
from imbue.mng.primitives import PluginName
from imbue.mng.primitives import ProviderInstanceName
from imbue.mng_kanpan.data_types import AgentBoardEntry
from imbue.mng_kanpan.data_types import BoardSection
from imbue.mng_kanpan.data_types import BoardSnapshot
from imbue.mng_kanpan.data_types import CheckStatus
from imbue.mng_kanpan.data_types import CustomCommand
from imbue.mng_kanpan.data_types import KanpanPluginConfig
from imbue.mng_kanpan.data_types import PrInfo
from imbue.mng_kanpan.data_types import PrState
from imbue.mng_kanpan.tui import _KanpanInputHandler
from imbue.mng_kanpan.tui import _KanpanState
from imbue.mng_kanpan.tui import _SelectableText
from imbue.mng_kanpan.tui import _build_board_widgets
from imbue.mng_kanpan.tui import _build_command_map
from imbue.mng_kanpan.tui import _cancel_delete
from imbue.mng_kanpan.tui import _classify_entry
from imbue.mng_kanpan.tui import _clear_focus
from imbue.mng_kanpan.tui import _confirm_delete
from imbue.mng_kanpan.tui import _delete_focused_agent
from imbue.mng_kanpan.tui import _dispatch_command
from imbue.mng_kanpan.tui import _execute_delete
from imbue.mng_kanpan.tui import _finish_delete
from imbue.mng_kanpan.tui import _finish_push
from imbue.mng_kanpan.tui import _finish_refresh
from imbue.mng_kanpan.tui import _format_agent_line
from imbue.mng_kanpan.tui import _format_check_markup
from imbue.mng_kanpan.tui import _format_push_status
from imbue.mng_kanpan.tui import _format_section_heading
from imbue.mng_kanpan.tui import _get_focused_entry
from imbue.mng_kanpan.tui import _get_state_attr
from imbue.mng_kanpan.tui import _is_focus_on_first_selectable
from imbue.mng_kanpan.tui import _is_safe_to_delete
from imbue.mng_kanpan.tui import _load_user_commands
from imbue.mng_kanpan.tui import _mute_focused_agent
from imbue.mng_kanpan.tui import _on_auto_refresh_alarm
from imbue.mng_kanpan.tui import _on_custom_command_poll
from imbue.mng_kanpan.tui import _on_delete_poll
from imbue.mng_kanpan.tui import _on_mute_persist_poll
from imbue.mng_kanpan.tui import _on_push_poll
from imbue.mng_kanpan.tui import _on_restore_footer
from imbue.mng_kanpan.tui import _on_spinner_tick
from imbue.mng_kanpan.tui import _push_focused_agent
from imbue.mng_kanpan.tui import _refresh_display
from imbue.mng_kanpan.tui import _restore_footer
from imbue.mng_kanpan.tui import _run_shell_command
from imbue.mng_kanpan.tui import _schedule_next_refresh
from imbue.mng_kanpan.tui import _show_transient_message
from imbue.mng_kanpan.tui import _start_refresh
from imbue.mng_kanpan.tui import _update_snapshot_mute
from imbue.mng_kanpan.tui import run_kanpan

# =============================================================================
# Helpers
# =============================================================================


def _make_entry(
    name: str = "test-agent",
    state: AgentLifecycleState = AgentLifecycleState.RUNNING,
    pr: PrInfo | None = None,
    work_dir: Path | None = None,
    commits_ahead: int | None = None,
    create_pr_url: str | None = None,
    is_muted: bool = False,
) -> AgentBoardEntry:
    return AgentBoardEntry(
        name=AgentName(name),
        state=state,
        provider_name=ProviderInstanceName("local"),
        work_dir=work_dir,
        pr=pr,
        commits_ahead=commits_ahead,
        create_pr_url=create_pr_url,
        is_muted=is_muted,
    )


def _make_pr(
    number: int = 42,
    state: PrState = PrState.OPEN,
    check_status: CheckStatus = CheckStatus.PASSING,
) -> PrInfo:
    return PrInfo(
        number=number,
        title="Test PR",
        state=state,
        url="https://github.com/owner/repo/pull/42",
        head_branch="mng/test-agent",
        check_status=check_status,
        is_draft=False,
    )


def _make_snapshot(
    entries: tuple[AgentBoardEntry, ...] = (),
    errors: tuple[str, ...] = (),
) -> BoardSnapshot:
    return BoardSnapshot(entries=entries, errors=errors, fetch_time_seconds=1.5)


def _make_state(
    snapshot: BoardSnapshot | None = None,
    commands: dict[str, CustomCommand] | None = None,
) -> _KanpanState:
    footer_left_text = Text("  Loading...")
    footer_left_attr = AttrMap(footer_left_text, "footer")
    footer_right = Text("r: refresh  q: quit")
    frame = MagicMock()
    mng_ctx = MagicMock()
    # Use model_construct to bypass Pydantic validation (MagicMock is not a real MngContext)
    return _KanpanState.model_construct(
        mng_ctx=mng_ctx,
        snapshot=snapshot,
        frame=frame,
        footer_left_text=footer_left_text,
        footer_left_attr=footer_left_attr,
        footer_right=footer_right,
        commands=commands or {},
        spinner_index=0,
        refresh_future=None,
        delete_future=None,
        deleting_agent_name=None,
        pending_delete_name=None,
        push_future=None,
        pushing_agent_name=None,
        executor=None,
        index_to_entry={},
        list_walker=None,
        focused_agent_name=None,
        steady_footer_text="  Loading...",
    )


# =============================================================================
# Tests for _SelectableText
# =============================================================================


def test_selectable_text_is_selectable() -> None:
    widget = _SelectableText("hello")
    assert widget.selectable() is True


def test_selectable_text_passes_keys_through() -> None:
    widget = _SelectableText("hello")
    result = widget.keypress((20,), "a")
    assert result == "a"


# =============================================================================
# Tests for _classify_entry
# =============================================================================


def test_classify_entry_muted_always_goes_to_muted_section() -> None:
    entry = _make_entry(is_muted=True, pr=_make_pr(state=PrState.MERGED))
    assert _classify_entry(entry) == BoardSection.MUTED


def test_classify_entry_no_pr_is_still_cooking() -> None:
    entry = _make_entry(pr=None)
    assert _classify_entry(entry) == BoardSection.STILL_COOKING


def test_classify_entry_merged_pr() -> None:
    entry = _make_entry(pr=_make_pr(state=PrState.MERGED))
    assert _classify_entry(entry) == BoardSection.PR_MERGED


def test_classify_entry_closed_pr() -> None:
    entry = _make_entry(pr=_make_pr(state=PrState.CLOSED))
    assert _classify_entry(entry) == BoardSection.PR_CLOSED


def test_classify_entry_open_pr() -> None:
    entry = _make_entry(pr=_make_pr(state=PrState.OPEN))
    assert _classify_entry(entry) == BoardSection.PR_BEING_REVIEWED


# =============================================================================
# Tests for _get_state_attr
# =============================================================================


def test_get_state_attr_running_gets_green() -> None:
    entry = _make_entry(state=AgentLifecycleState.RUNNING)
    assert _get_state_attr(entry, BoardSection.STILL_COOKING) == "state_running"


def test_get_state_attr_waiting_in_still_cooking_gets_attention() -> None:
    entry = _make_entry(state=AgentLifecycleState.WAITING)
    assert _get_state_attr(entry, BoardSection.STILL_COOKING) == "state_attention"


def test_get_state_attr_waiting_in_review_gets_no_color() -> None:
    entry = _make_entry(state=AgentLifecycleState.WAITING)
    assert _get_state_attr(entry, BoardSection.PR_BEING_REVIEWED) == ""


def test_get_state_attr_stopped_gets_no_color() -> None:
    entry = _make_entry(state=AgentLifecycleState.STOPPED)
    assert _get_state_attr(entry, BoardSection.STILL_COOKING) == ""


# =============================================================================
# Tests for _format_check_markup
# =============================================================================


def test_format_check_markup_no_pr_returns_empty() -> None:
    entry = _make_entry(pr=None)
    assert _format_check_markup(entry) == []


def test_format_check_markup_unknown_returns_empty() -> None:
    entry = _make_entry(pr=_make_pr(check_status=CheckStatus.UNKNOWN))
    assert _format_check_markup(entry) == []


def test_format_check_markup_failing_gets_color() -> None:
    entry = _make_entry(pr=_make_pr(check_status=CheckStatus.FAILING))
    markup = _format_check_markup(entry)
    assert len(markup) == 2
    assert markup[0] == "  CI "
    assert markup[1] == ("check_failing", "failing")


def test_format_check_markup_pending_gets_color() -> None:
    entry = _make_entry(pr=_make_pr(check_status=CheckStatus.PENDING))
    markup = _format_check_markup(entry)
    assert len(markup) == 2
    assert markup[1] == ("check_pending", "pending")


def test_format_check_markup_passing_gets_default_color() -> None:
    entry = _make_entry(pr=_make_pr(check_status=CheckStatus.PASSING))
    markup = _format_check_markup(entry)
    assert len(markup) == 1
    assert "passing" in markup[0]


# =============================================================================
# Tests for _format_push_status
# =============================================================================


def test_format_push_status_none_shows_not_pushed() -> None:
    entry = _make_entry(commits_ahead=None)
    assert _format_push_status(entry) == "  [not pushed]"


def test_format_push_status_zero_shows_up_to_date() -> None:
    entry = _make_entry(commits_ahead=0)
    assert _format_push_status(entry) == "  [up to date]"


def test_format_push_status_positive_shows_count() -> None:
    entry = _make_entry(commits_ahead=3)
    assert _format_push_status(entry) == "  [3 unpushed]"


# =============================================================================
# Tests for _format_section_heading
# =============================================================================


def test_format_section_heading_merged() -> None:
    markup = _format_section_heading(BoardSection.PR_MERGED, 5)
    assert markup[0] == ("section_done", "Done")
    assert "PR merged" in markup[1]
    assert "(5)" in markup[1]


def test_format_section_heading_muted_has_no_suffix() -> None:
    markup = _format_section_heading(BoardSection.MUTED, 2)
    assert markup[0] == ("section_muted", "Muted")
    assert "(2)" in markup[1]


def test_format_section_heading_still_cooking() -> None:
    markup = _format_section_heading(BoardSection.STILL_COOKING, 1)
    assert markup[0] == ("section_in_progress", "In progress")
    assert "no PR yet" in markup[1]


# =============================================================================
# Tests for _format_agent_line
# =============================================================================


def test_format_agent_line_basic() -> None:
    entry = _make_entry(name="my-agent", state=AgentLifecycleState.RUNNING)
    markup = _format_agent_line(entry, BoardSection.STILL_COOKING)
    text = "".join(seg if isinstance(seg, str) else seg[1] for seg in markup)
    assert "my-agent" in text
    assert "RUNNING" in text


def test_format_agent_line_with_pr() -> None:
    entry = _make_entry(pr=_make_pr(number=99))
    markup = _format_agent_line(entry, BoardSection.PR_BEING_REVIEWED)
    text = "".join(seg if isinstance(seg, str) else seg[1] for seg in markup)
    assert "PR #99" in text


def test_format_agent_line_with_create_pr_url() -> None:
    entry = _make_entry(create_pr_url="https://github.com/owner/repo/compare/branch?expand=1")
    markup = _format_agent_line(entry, BoardSection.STILL_COOKING)
    text = "".join(seg if isinstance(seg, str) else seg[1] for seg in markup)
    assert "create PR:" in text


def test_format_agent_line_muted_flattens_to_gray() -> None:
    entry = _make_entry(is_muted=True, state=AgentLifecycleState.RUNNING)
    markup = _format_agent_line(entry, BoardSection.MUTED)
    assert len(markup) == 1
    assert markup[0][0] == "muted"


def test_format_agent_line_with_work_dir_shows_push_status() -> None:
    entry = _make_entry(work_dir=Path("/tmp/work"), commits_ahead=2)
    markup = _format_agent_line(entry, BoardSection.STILL_COOKING)
    text = "".join(seg if isinstance(seg, str) else seg[1] for seg in markup)
    assert "[2 unpushed]" in text


# =============================================================================
# Tests for _is_safe_to_delete
# =============================================================================


def test_is_safe_to_delete_merged_pr() -> None:
    entry = _make_entry(pr=_make_pr(state=PrState.MERGED))
    assert _is_safe_to_delete(entry) is True


def test_is_safe_to_delete_open_pr() -> None:
    entry = _make_entry(pr=_make_pr(state=PrState.OPEN))
    assert _is_safe_to_delete(entry) is False


def test_is_safe_to_delete_no_pr() -> None:
    entry = _make_entry(pr=None)
    assert _is_safe_to_delete(entry) is False


def test_is_safe_to_delete_closed_pr() -> None:
    entry = _make_entry(pr=_make_pr(state=PrState.CLOSED))
    assert _is_safe_to_delete(entry) is False


# =============================================================================
# Tests for _build_board_widgets
# =============================================================================


def test_build_board_widgets_none_snapshot_shows_loading() -> None:
    state = _make_state(snapshot=None)
    walker = _build_board_widgets(state)
    assert len(walker) == 1
    assert isinstance(walker[0], Text)


def test_build_board_widgets_empty_snapshot_shows_no_agents() -> None:
    state = _make_state(snapshot=_make_snapshot())
    walker = _build_board_widgets(state)
    assert len(walker) == 1
    text_content = str(walker[0].get_text()[0])
    assert "No agents found" in text_content


def test_build_board_widgets_with_entries_creates_sections() -> None:
    entries = (
        _make_entry(name="cooking", state=AgentLifecycleState.RUNNING),
        _make_entry(name="merged", pr=_make_pr(state=PrState.MERGED)),
    )
    state = _make_state(snapshot=_make_snapshot(entries=entries))
    walker = _build_board_widgets(state)
    # Should have: section heading + agent for merged, divider, section heading + agent for cooking
    assert len(walker) >= 4
    # index_to_entry should have 2 agent entries
    assert len(state.index_to_entry) == 2


def test_build_board_widgets_populates_index_to_entry() -> None:
    entries = (
        _make_entry(name="agent-a"),
        _make_entry(name="agent-b"),
    )
    state = _make_state(snapshot=_make_snapshot(entries=entries))
    _build_board_widgets(state)
    names = {entry.name for entry in state.index_to_entry.values()}
    assert AgentName("agent-a") in names
    assert AgentName("agent-b") in names


def test_build_board_widgets_with_errors_shows_them() -> None:
    state = _make_state(snapshot=_make_snapshot(errors=("Something went wrong",)))
    walker = _build_board_widgets(state)
    all_text = " ".join(str(w.get_text()[0]) for w in walker if isinstance(w, Text))
    assert "Errors:" in all_text
    assert "Something went wrong" in all_text


# =============================================================================
# Tests for _get_focused_entry and _is_focus_on_first_selectable
# =============================================================================


def test_get_focused_entry_returns_none_when_no_walker() -> None:
    state = _make_state()
    assert _get_focused_entry(state) is None


def test_get_focused_entry_returns_entry_when_focused() -> None:
    entries = (_make_entry(name="focused-agent"),)
    state = _make_state(snapshot=_make_snapshot(entries=entries))
    walker = _build_board_widgets(state)
    state.list_walker = walker
    # Focus on the agent entry (not the section heading)
    agent_idx = next(iter(state.index_to_entry.keys()))
    walker.set_focus(agent_idx)
    entry = _get_focused_entry(state)
    assert entry is not None
    assert entry.name == AgentName("focused-agent")


def test_is_focus_on_first_selectable_true() -> None:
    entries = (_make_entry(name="only-agent"),)
    state = _make_state(snapshot=_make_snapshot(entries=entries))
    walker = _build_board_widgets(state)
    state.list_walker = walker
    first_idx = min(state.index_to_entry.keys())
    walker.set_focus(first_idx)
    assert _is_focus_on_first_selectable(state) is True


def test_is_focus_on_first_selectable_false_when_no_walker() -> None:
    state = _make_state()
    assert _is_focus_on_first_selectable(state) is False


def test_clear_focus_moves_to_top() -> None:
    entries = (
        _make_entry(name="agent-a"),
        _make_entry(name="agent-b"),
    )
    state = _make_state(snapshot=_make_snapshot(entries=entries))
    walker = _build_board_widgets(state)
    state.list_walker = walker
    # Focus on the last agent
    last_idx = max(state.index_to_entry.keys())
    walker.set_focus(last_idx)
    _clear_focus(state)
    assert state.focused_agent_name is None
    _, focus_pos = walker.get_focus()
    assert focus_pos == 0


# =============================================================================
# Tests for _update_snapshot_mute
# =============================================================================


def test_update_snapshot_mute_sets_muted() -> None:
    entries = (
        _make_entry(name="agent-a", is_muted=False),
        _make_entry(name="agent-b", is_muted=False),
    )
    state = _make_state(snapshot=_make_snapshot(entries=entries))
    _update_snapshot_mute(state, AgentName("agent-a"), True)
    assert state.snapshot is not None
    updated = {e.name: e for e in state.snapshot.entries}
    assert updated[AgentName("agent-a")].is_muted is True
    assert updated[AgentName("agent-b")].is_muted is False


def test_update_snapshot_mute_unsets_muted() -> None:
    entries = (_make_entry(name="agent-a", is_muted=True),)
    state = _make_state(snapshot=_make_snapshot(entries=entries))
    _update_snapshot_mute(state, AgentName("agent-a"), False)
    assert state.snapshot is not None
    assert state.snapshot.entries[0].is_muted is False


def test_update_snapshot_mute_no_snapshot_is_noop() -> None:
    state = _make_state(snapshot=None)
    _update_snapshot_mute(state, AgentName("agent-a"), True)
    assert state.snapshot is None


# =============================================================================
# Tests for _KanpanInputHandler
# =============================================================================


def test_input_handler_q_exits() -> None:
    state = _make_state()
    handler = _KanpanInputHandler(state=state)
    with pytest.raises(ExitMainLoop):
        handler("q")


def test_input_handler_uppercase_q_exits() -> None:
    state = _make_state()
    handler = _KanpanInputHandler(state=state)
    with pytest.raises(ExitMainLoop):
        handler("Q")


def test_input_handler_ctrl_c_exits() -> None:
    state = _make_state()
    handler = _KanpanInputHandler(state=state)
    with pytest.raises(ExitMainLoop):
        handler("ctrl c")


def test_input_handler_ignores_mouse_events() -> None:
    state = _make_state()
    handler = _KanpanInputHandler(state=state)
    result = handler(("mouse press", 1, 0, 0))
    assert result is None


def test_input_handler_passes_through_navigation_keys() -> None:
    state = _make_state()
    handler = _KanpanInputHandler(state=state)
    assert handler("down") is None
    assert handler("page up") is None
    assert handler("page down") is None
    assert handler("home") is None
    assert handler("end") is None


def test_input_handler_swallows_unknown_keys() -> None:
    state = _make_state()
    handler = _KanpanInputHandler(state=state)
    result = handler("x")
    assert result is True


def test_input_handler_pending_delete_y_confirms() -> None:
    state = _make_state()
    state.pending_delete_name = AgentName("doomed-agent")
    handler = _KanpanInputHandler(state=state)
    # y confirms; since there's no executor, _confirm_delete will clear pending
    # and try to execute (but won't because there's no loop). The key is it doesn't raise.
    result = handler("y")
    assert result is True
    assert state.pending_delete_name is None


def test_input_handler_pending_delete_other_key_cancels() -> None:
    state = _make_state()
    state.pending_delete_name = AgentName("doomed-agent")
    handler = _KanpanInputHandler(state=state)
    result = handler("n")
    assert result is True
    assert state.pending_delete_name is None


def test_input_handler_up_on_first_selectable_clears_focus() -> None:
    entries = (_make_entry(name="agent-a"),)
    state = _make_state(snapshot=_make_snapshot(entries=entries))
    walker = _build_board_widgets(state)
    state.list_walker = walker
    first_idx = min(state.index_to_entry.keys())
    walker.set_focus(first_idx)
    handler = _KanpanInputHandler(state=state)
    result = handler("up")
    assert result is True
    assert state.focused_agent_name is None


# =============================================================================
# Tests for _build_command_map
# =============================================================================


def test_build_command_map_returns_builtins_with_no_user_config() -> None:
    mng_ctx = MagicMock()
    mng_ctx.config.plugins = {}
    commands = _build_command_map(mng_ctx)
    assert "r" in commands
    assert "p" in commands
    assert "d" in commands
    assert "m" in commands


def test_build_command_map_user_command_overrides_builtin() -> None:
    mng_ctx = MagicMock()
    mng_ctx.config.plugins = {
        PluginName("kanpan"): KanpanPluginConfig(
            commands={"r": CustomCommand(name="custom-refresh", command="echo refresh")}
        )
    }
    commands = _build_command_map(mng_ctx)
    assert commands["r"].name == "custom-refresh"
    assert commands["r"].command == "echo refresh"


def test_build_command_map_disabled_command_is_excluded() -> None:
    mng_ctx = MagicMock()
    mng_ctx.config.plugins = {
        PluginName("kanpan"): KanpanPluginConfig(commands={"d": CustomCommand(name="delete", enabled=False)})
    }
    commands = _build_command_map(mng_ctx)
    assert "d" not in commands


def test_build_command_map_adds_user_defined_key() -> None:
    mng_ctx = MagicMock()
    mng_ctx.config.plugins = {
        PluginName("kanpan"): KanpanPluginConfig(commands={"x": CustomCommand(name="custom", command="echo custom")})
    }
    commands = _build_command_map(mng_ctx)
    assert "x" in commands
    assert commands["x"].name == "custom"


# =============================================================================
# Tests for _show_transient_message and _restore_footer
# =============================================================================


def test_show_transient_message_updates_footer() -> None:
    state = _make_state()
    _show_transient_message(state, "  Operation succeeded")
    assert state.footer_left_text.get_text()[0] == "  Operation succeeded"


def test_restore_footer_restores_steady_state() -> None:
    state = _make_state()
    state.steady_footer_text = "  Last refresh: 12:00:00"
    _show_transient_message(state, "  Temporary message")
    _restore_footer(state)
    assert state.footer_left_text.get_text()[0] == "  Last refresh: 12:00:00"


# =============================================================================
# Tests for _cancel_delete
# =============================================================================


def test_cancel_delete_clears_pending_and_restores_footer() -> None:
    state = _make_state()
    state.pending_delete_name = AgentName("agent-to-cancel")
    state.steady_footer_text = "  Steady state"
    _cancel_delete(state)
    assert state.pending_delete_name is None
    assert state.footer_left_text.get_text()[0] == "  Steady state"


# =============================================================================
# Tests for _dispatch_command
# =============================================================================


def test_dispatch_command_refresh_builtin_without_loop_is_noop() -> None:
    state = _make_state()
    cmd = CustomCommand(name="refresh")
    _dispatch_command(state, "r", cmd)
    # No crash, no state change (no loop set)


def test_dispatch_command_delete_builtin_without_focus_is_noop() -> None:
    state = _make_state()
    cmd = CustomCommand(name="delete")
    _dispatch_command(state, "d", cmd)
    # No focused entry, so nothing happens


def test_dispatch_command_push_builtin_without_focus_is_noop() -> None:
    state = _make_state()
    cmd = CustomCommand(name="push")
    _dispatch_command(state, "p", cmd)
    # No focused entry, so nothing happens


def test_dispatch_command_mute_builtin_without_focus_is_noop() -> None:
    state = _make_state()
    cmd = CustomCommand(name="mute")
    _dispatch_command(state, "m", cmd)
    # No focused entry, so nothing happens


# =============================================================================
# Tests for _delete_focused_agent
# =============================================================================


def test_delete_focused_agent_already_deleting_is_noop() -> None:
    state = _make_state()
    state.delete_future = MagicMock()
    _delete_focused_agent(state)
    # Should return early, no crash


def test_delete_focused_agent_no_focus_is_noop() -> None:
    state = _make_state()
    _delete_focused_agent(state)
    # No focused entry, no crash


def test_delete_focused_agent_non_merged_prompts_confirmation() -> None:
    entries = (_make_entry(name="unmerged-agent", pr=_make_pr(state=PrState.OPEN)),)
    state = _make_state(snapshot=_make_snapshot(entries=entries))
    walker = _build_board_widgets(state)
    state.list_walker = walker
    agent_idx = next(iter(state.index_to_entry.keys()))
    walker.set_focus(agent_idx)
    _delete_focused_agent(state)
    assert state.pending_delete_name == AgentName("unmerged-agent")
    assert "confirm" in state.footer_left_text.get_text()[0].lower()


# =============================================================================
# Tests for _push_focused_agent
# =============================================================================


def test_push_focused_agent_already_pushing_is_noop() -> None:
    state = _make_state()
    state.push_future = MagicMock()
    _push_focused_agent(state)
    # Should return early


def test_push_focused_agent_no_focus_is_noop() -> None:
    state = _make_state()
    _push_focused_agent(state)
    # No focused entry


def test_push_focused_agent_no_work_dir_shows_message() -> None:
    entries = (_make_entry(name="remote-agent", work_dir=None),)
    state = _make_state(snapshot=_make_snapshot(entries=entries))
    walker = _build_board_widgets(state)
    state.list_walker = walker
    agent_idx = next(iter(state.index_to_entry.keys()))
    walker.set_focus(agent_idx)
    _push_focused_agent(state)
    assert "Cannot push" in state.footer_left_text.get_text()[0]


# =============================================================================
# Tests for _refresh_display
# =============================================================================


def test_refresh_display_rebuilds_body() -> None:
    entries = (
        _make_entry(name="agent-a"),
        _make_entry(name="agent-b"),
    )
    state = _make_state(snapshot=_make_snapshot(entries=entries))
    _refresh_display(state)
    assert state.list_walker is not None
    assert len(state.index_to_entry) == 2


def test_refresh_display_preserves_focus_by_name() -> None:
    entries = (
        _make_entry(name="agent-a"),
        _make_entry(name="agent-b"),
    )
    state = _make_state(snapshot=_make_snapshot(entries=entries))
    _refresh_display(state)
    # Focus on agent-b
    for idx, entry in state.index_to_entry.items():
        if entry.name == AgentName("agent-b"):
            state.list_walker.set_focus(idx)
            break
    # Refresh again - should restore focus to agent-b
    _refresh_display(state)
    focused = _get_focused_entry(state)
    assert focused is not None
    assert focused.name == AgentName("agent-b")


# =============================================================================
# Tests for _on_restore_footer callback
# =============================================================================


def test_on_restore_footer_callback_restores_footer() -> None:
    state = _make_state()
    state.steady_footer_text = "  Steady state text"
    _show_transient_message(state, "  Temporary")
    loop = MagicMock()
    _on_restore_footer(loop, state)
    assert state.footer_left_text.get_text()[0] == "  Steady state text"


# =============================================================================
# Tests for _confirm_delete
# =============================================================================


def test_confirm_delete_clears_pending_and_resets_attr() -> None:
    state = _make_state()
    state.pending_delete_name = AgentName("agent-to-delete")
    _confirm_delete(state)
    assert state.pending_delete_name is None


def test_confirm_delete_with_none_pending_is_noop() -> None:
    state = _make_state()
    state.pending_delete_name = None
    _confirm_delete(state)
    # No crash, no executor creation


# =============================================================================
# Tests for _execute_delete
# =============================================================================


def test_execute_delete_sets_footer_and_creates_executor(monkeypatch: pytest.MonkeyPatch) -> None:
    state = _make_state()
    # Monkeypatch _run_destroy to avoid subprocess
    monkeypatch.setattr(
        "imbue.mng_kanpan.tui._run_destroy",
        lambda name: subprocess.CompletedProcess(args=[], returncode=0),
    )
    _execute_delete(state, AgentName("test-agent"))
    assert state.deleting_agent_name == AgentName("test-agent")
    assert "Deleting test-agent" in state.footer_left_text.get_text()[0]
    assert state.delete_future is not None
    assert state.executor is not None
    state.executor.shutdown(wait=True)


# =============================================================================
# Tests for _on_delete_poll and _finish_delete
# =============================================================================


def _make_done_future(result: subprocess.CompletedProcess[str]) -> Future[subprocess.CompletedProcess[str]]:
    future: Future[subprocess.CompletedProcess[str]] = Future()
    future.set_result(result)
    return future


def _make_failed_future(error: Exception) -> Future[subprocess.CompletedProcess[str]]:
    future: Future[subprocess.CompletedProcess[str]] = Future()
    future.set_exception(error)
    return future


def test_on_delete_poll_no_future_is_noop() -> None:
    state = _make_state()
    state.delete_future = None
    loop = MagicMock()
    _on_delete_poll(loop, state)
    # No crash


def test_on_delete_poll_with_done_future_calls_finish() -> None:
    entries = (_make_entry(name="agent-a"),)
    state = _make_state(snapshot=_make_snapshot(entries=entries))
    state.delete_future = _make_done_future(subprocess.CompletedProcess(args=[], returncode=0))
    state.deleting_agent_name = AgentName("agent-a")
    loop = MagicMock()
    _on_delete_poll(loop, state)
    # _finish_delete should have been called, clearing delete_future
    assert state.delete_future is None


def test_on_delete_poll_not_done_schedules_next_tick() -> None:
    state = _make_state()
    state.delete_future = Future()  # Not done
    state.deleting_agent_name = AgentName("agent-a")
    loop = MagicMock()
    _on_delete_poll(loop, state)
    loop.set_alarm_in.assert_called_once()


def test_finish_delete_success_shows_message() -> None:
    entries = (_make_entry(name="agent-a"),)
    state = _make_state(snapshot=_make_snapshot(entries=entries))
    state.delete_future = _make_done_future(subprocess.CompletedProcess(args=[], returncode=0))
    state.deleting_agent_name = AgentName("agent-a")
    loop = MagicMock()
    _finish_delete(loop, state)
    assert state.delete_future is None
    assert state.deleting_agent_name is None
    assert "Deleted agent-a" in state.footer_left_text.get_text()[0]


def test_finish_delete_failure_shows_error() -> None:
    entries = (_make_entry(name="agent-a"),)
    state = _make_state(snapshot=_make_snapshot(entries=entries))
    state.delete_future = _make_done_future(subprocess.CompletedProcess(args=[], returncode=1, stderr="some error"))
    state.deleting_agent_name = AgentName("agent-a")
    loop = MagicMock()
    _finish_delete(loop, state)
    assert "Failed to delete" in state.footer_left_text.get_text()[0]


def test_finish_delete_exception_shows_error() -> None:
    entries = (_make_entry(name="agent-a"),)
    state = _make_state(snapshot=_make_snapshot(entries=entries))
    state.delete_future = _make_failed_future(RuntimeError("connection lost"))
    state.deleting_agent_name = AgentName("agent-a")
    loop = MagicMock()
    _finish_delete(loop, state)
    assert "Failed to delete" in state.footer_left_text.get_text()[0]


def test_finish_delete_no_future_is_noop() -> None:
    state = _make_state()
    state.delete_future = None
    loop = MagicMock()
    _finish_delete(loop, state)


# =============================================================================
# Tests for _on_push_poll and _finish_push
# =============================================================================


def test_on_push_poll_no_future_is_noop() -> None:
    state = _make_state()
    state.push_future = None
    loop = MagicMock()
    _on_push_poll(loop, state)


def test_on_push_poll_done_future_calls_finish() -> None:
    entries = (_make_entry(name="agent-a"),)
    state = _make_state(snapshot=_make_snapshot(entries=entries))
    state.push_future = _make_done_future(subprocess.CompletedProcess(args=[], returncode=0))
    state.pushing_agent_name = AgentName("agent-a")
    loop = MagicMock()
    _on_push_poll(loop, state)
    assert state.push_future is None


def test_on_push_poll_not_done_schedules_next() -> None:
    state = _make_state()
    state.push_future = Future()
    state.pushing_agent_name = AgentName("agent-a")
    loop = MagicMock()
    _on_push_poll(loop, state)
    loop.set_alarm_in.assert_called_once()


def test_finish_push_success_shows_message() -> None:
    entries = (_make_entry(name="agent-a"),)
    state = _make_state(snapshot=_make_snapshot(entries=entries))
    state.push_future = _make_done_future(subprocess.CompletedProcess(args=[], returncode=0))
    state.pushing_agent_name = AgentName("agent-a")
    loop = MagicMock()
    _finish_push(loop, state)
    assert state.push_future is None
    assert "Pushed agent-a" in state.footer_left_text.get_text()[0]


def test_finish_push_failure_shows_error() -> None:
    entries = (_make_entry(name="agent-a"),)
    state = _make_state(snapshot=_make_snapshot(entries=entries))
    state.push_future = _make_done_future(subprocess.CompletedProcess(args=[], returncode=1, stderr="rejected"))
    state.pushing_agent_name = AgentName("agent-a")
    loop = MagicMock()
    _finish_push(loop, state)
    assert "Failed to push" in state.footer_left_text.get_text()[0]


def test_finish_push_exception_shows_error() -> None:
    entries = (_make_entry(name="agent-a"),)
    state = _make_state(snapshot=_make_snapshot(entries=entries))
    state.push_future = _make_failed_future(RuntimeError("timeout"))
    state.pushing_agent_name = AgentName("agent-a")
    loop = MagicMock()
    _finish_push(loop, state)
    assert "Failed to push" in state.footer_left_text.get_text()[0]


# =============================================================================
# Tests for _on_spinner_tick and _start_refresh
# =============================================================================


def test_on_spinner_tick_no_future_is_noop() -> None:
    state = _make_state()
    state.refresh_future = None
    loop = MagicMock()
    _on_spinner_tick(loop, state)


def test_on_spinner_tick_not_done_animates() -> None:
    state = _make_state()
    state.refresh_future = Future()
    loop = MagicMock()
    _on_spinner_tick(loop, state)
    assert "Refreshing" in state.footer_left_text.get_text()[0]
    loop.set_alarm_in.assert_called_once()


def test_on_spinner_tick_done_finishes_refresh() -> None:
    entries = (_make_entry(name="agent-a"),)
    snapshot = _make_snapshot(entries=entries)
    state = _make_state(snapshot=snapshot)
    done_future: Future[BoardSnapshot] = Future()
    done_future.set_result(snapshot)
    state.refresh_future = done_future
    loop = MagicMock()
    _on_spinner_tick(loop, state)
    assert state.refresh_future is None


def test_start_refresh_creates_executor_and_schedules_spinner(monkeypatch: pytest.MonkeyPatch) -> None:
    state = _make_state()
    # Monkeypatch fetch_board_snapshot to return a snapshot immediately
    monkeypatch.setattr(
        "imbue.mng_kanpan.tui.fetch_board_snapshot",
        lambda ctx: _make_snapshot(),
    )
    loop = MagicMock()
    _start_refresh(loop, state)
    assert state.executor is not None
    assert state.refresh_future is not None
    loop.set_alarm_in.assert_called_once()
    state.executor.shutdown(wait=True)


def test_schedule_next_refresh_sets_alarm() -> None:
    state = _make_state()
    loop = MagicMock()
    _schedule_next_refresh(loop, state)
    loop.set_alarm_in.assert_called_once()


# =============================================================================
# Tests for _finish_refresh
# =============================================================================


def test_finish_refresh_updates_snapshot_and_display() -> None:
    entries = (_make_entry(name="agent-a"),)
    snapshot = _make_snapshot(entries=entries)
    state = _make_state(snapshot=None)
    done_future: Future[BoardSnapshot] = Future()
    done_future.set_result(snapshot)
    state.refresh_future = done_future
    loop = MagicMock()
    _finish_refresh(loop, state)
    assert state.snapshot is not None
    assert state.refresh_future is None
    assert "Last refresh" in state.footer_left_text.get_text()[0]


def test_finish_refresh_handles_exception() -> None:
    old_snapshot = _make_snapshot(entries=(_make_entry(name="old-agent"),))
    state = _make_state(snapshot=old_snapshot)
    failed_future: Future[BoardSnapshot] = Future()
    failed_future.set_exception(RuntimeError("fetch failed"))
    state.refresh_future = failed_future
    loop = MagicMock()
    _finish_refresh(loop, state)
    assert state.refresh_future is None
    # Old entries should still be present, errors appended
    assert state.snapshot is not None
    assert any("Refresh failed" in e for e in state.snapshot.errors)


def test_finish_refresh_no_future_is_noop() -> None:
    state = _make_state()
    state.refresh_future = None
    loop = MagicMock()
    _finish_refresh(loop, state)


# =============================================================================
# Tests for _on_custom_command_poll
# =============================================================================


def test_on_custom_command_poll_done_success() -> None:
    state = _make_state()
    future = _make_done_future(subprocess.CompletedProcess(args=[], returncode=0))
    cmd = CustomCommand(name="test-cmd", command="echo hello")
    loop = MagicMock()
    _on_custom_command_poll(loop, (state, future, cmd, AgentName("agent-a")))
    assert "test-cmd completed" in state.footer_left_text.get_text()[0]


def test_on_custom_command_poll_done_failure() -> None:
    state = _make_state()
    future = _make_done_future(subprocess.CompletedProcess(args=[], returncode=1, stderr="oops"))
    cmd = CustomCommand(name="test-cmd", command="echo hello")
    loop = MagicMock()
    _on_custom_command_poll(loop, (state, future, cmd, AgentName("agent-a")))
    assert "test-cmd failed" in state.footer_left_text.get_text()[0]


def test_on_custom_command_poll_done_exception() -> None:
    state = _make_state()
    future = _make_failed_future(RuntimeError("boom"))
    cmd = CustomCommand(name="test-cmd", command="echo hello")
    loop = MagicMock()
    _on_custom_command_poll(loop, (state, future, cmd, AgentName("agent-a")))
    assert "test-cmd failed" in state.footer_left_text.get_text()[0]


def test_on_custom_command_poll_not_done_animates() -> None:
    state = _make_state()
    future: Future[subprocess.CompletedProcess[str]] = Future()
    cmd = CustomCommand(name="test-cmd", command="echo hello")
    loop = MagicMock()
    _on_custom_command_poll(loop, (state, future, cmd, AgentName("agent-a")))
    assert "Running test-cmd" in state.footer_left_text.get_text()[0]
    loop.set_alarm_in.assert_called_once()


def test_on_custom_command_poll_refreshes_afterwards() -> None:
    entries = (_make_entry(name="agent-a"),)
    state = _make_state(snapshot=_make_snapshot(entries=entries))
    future = _make_done_future(subprocess.CompletedProcess(args=[], returncode=0))
    cmd = CustomCommand(name="test-cmd", command="echo hello", refresh_afterwards=True)
    loop = MagicMock()
    _on_custom_command_poll(loop, (state, future, cmd, AgentName("agent-a")))
    # Should trigger a refresh after completion


# =============================================================================
# Tests for _mute_focused_agent
# =============================================================================


def test_mute_focused_agent_no_focus_is_noop() -> None:
    state = _make_state()
    _mute_focused_agent(state)
    # No crash


def test_mute_focused_agent_toggles_and_updates_ui() -> None:
    entries = (_make_entry(name="agent-to-mute", is_muted=False),)
    state = _make_state(snapshot=_make_snapshot(entries=entries))
    walker = _build_board_widgets(state)
    state.list_walker = walker
    agent_idx = next(iter(state.index_to_entry.keys()))
    walker.set_focus(agent_idx)
    _mute_focused_agent(state)
    assert state.snapshot is not None
    assert state.snapshot.entries[0].is_muted is True
    assert "Muted" in state.footer_left_text.get_text()[0]
    assert state.executor is not None
    state.executor.shutdown(wait=False)


# =============================================================================
# Tests for _run_shell_command
# =============================================================================


def test_run_shell_command_no_focus_is_noop() -> None:
    state = _make_state()
    cmd = CustomCommand(name="test", command="echo hello")
    _run_shell_command(state, cmd)
    # No crash


# =============================================================================
# Tests for _dispatch_command with custom commands
# =============================================================================


def test_dispatch_command_custom_shell_command(monkeypatch: pytest.MonkeyPatch) -> None:
    entries = (_make_entry(name="agent-a"),)
    state = _make_state(snapshot=_make_snapshot(entries=entries))
    walker = _build_board_widgets(state)
    state.list_walker = walker
    agent_idx = next(iter(state.index_to_entry.keys()))
    walker.set_focus(agent_idx)
    cmd = CustomCommand(name="custom", command="echo hello")
    _dispatch_command(state, "x", cmd)
    assert "Running custom" in state.footer_left_text.get_text()[0]
    assert state.executor is not None
    state.executor.shutdown(wait=True)


# =============================================================================
# Tests for _load_user_commands with dict-typed commands
# =============================================================================


def test_load_user_commands_parses_dict_as_custom_command() -> None:
    mng_ctx = MagicMock()
    mng_ctx.config.plugins = {
        PluginName("kanpan"): KanpanPluginConfig(commands={"x": CustomCommand(name="from-model", command="echo test")})
    }
    commands = _load_user_commands(mng_ctx)
    assert "x" in commands
    assert commands["x"].name == "from-model"


def test_load_user_commands_no_kanpan_plugin_returns_empty() -> None:
    mng_ctx = MagicMock()
    mng_ctx.config.plugins = {}
    commands = _load_user_commands(mng_ctx)
    assert commands == {}


def test_load_user_commands_wrong_plugin_type_returns_empty() -> None:
    mng_ctx = MagicMock()
    mng_ctx.config.plugins = {PluginName("kanpan"): "not-a-config"}
    commands = _load_user_commands(mng_ctx)
    assert commands == {}


# =============================================================================
# Tests for _delete_focused_agent with safe-to-delete (merged PR)
# =============================================================================


def test_delete_focused_agent_merged_pr_executes_immediately(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "imbue.mng_kanpan.tui._run_destroy",
        lambda name: subprocess.CompletedProcess(args=[], returncode=0),
    )
    entries = (_make_entry(name="merged-agent", pr=_make_pr(state=PrState.MERGED)),)
    state = _make_state(snapshot=_make_snapshot(entries=entries))
    walker = _build_board_widgets(state)
    state.list_walker = walker
    agent_idx = next(iter(state.index_to_entry.keys()))
    walker.set_focus(agent_idx)
    _delete_focused_agent(state)
    # Safe to delete, so no confirmation needed
    assert state.pending_delete_name is None
    assert state.deleting_agent_name == AgentName("merged-agent")
    assert state.executor is not None
    state.executor.shutdown(wait=True)


# =============================================================================
# Tests for _on_auto_refresh_alarm
# =============================================================================


def test_on_auto_refresh_alarm_starts_refresh(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "imbue.mng_kanpan.tui.fetch_board_snapshot",
        lambda ctx: _make_snapshot(),
    )
    state = _make_state()
    state.refresh_future = None
    loop = MagicMock()
    _on_auto_refresh_alarm(loop, state)
    assert state.refresh_future is not None
    assert state.executor is not None
    state.executor.shutdown(wait=True)


def test_on_auto_refresh_alarm_skips_if_already_refreshing() -> None:
    state = _make_state()
    state.refresh_future = Future()  # Already refreshing
    loop = MagicMock()
    _on_auto_refresh_alarm(loop, state)
    # Should not start another refresh


# =============================================================================
# Tests for _on_mute_persist_poll
# =============================================================================


def test_on_mute_persist_poll_success() -> None:
    state = _make_state(snapshot=_make_snapshot(entries=(_make_entry(name="a", is_muted=True),)))
    future: Future[bool] = Future()
    future.set_result(True)
    loop = MagicMock()
    _on_mute_persist_poll(loop, (state, future, AgentName("a"), True))
    # Success, no revert


def test_on_mute_persist_poll_failure_reverts() -> None:
    entries = (_make_entry(name="a", is_muted=True),)
    state = _make_state(snapshot=_make_snapshot(entries=entries))
    _refresh_display(state)
    future: Future[bool] = Future()
    future.set_exception(RuntimeError("persist failed"))
    loop = MagicMock()
    _on_mute_persist_poll(loop, (state, future, AgentName("a"), True))
    # Should revert mute
    assert state.snapshot is not None
    assert state.snapshot.entries[0].is_muted is False


def test_on_mute_persist_poll_not_done_schedules_next() -> None:
    state = _make_state()
    future: Future[bool] = Future()
    loop = MagicMock()
    _on_mute_persist_poll(loop, (state, future, AgentName("a"), True))
    loop.set_alarm_in.assert_called_once()


# =============================================================================
# Tests for run_kanpan (mocked MainLoop)
# =============================================================================


def test_run_kanpan_creates_and_runs_loop(
    monkeypatch: pytest.MonkeyPatch,
    temp_mng_ctx: object,
) -> None:
    monkeypatch.setattr("imbue.mng_kanpan.tui.Screen", lambda: MagicMock())

    def mock_main_loop(*args, **kwargs):  # type: ignore[no-untyped-def]
        return MagicMock()

    monkeypatch.setattr("imbue.mng_kanpan.tui.MainLoop", mock_main_loop)
    monkeypatch.setattr(
        "imbue.mng_kanpan.tui.fetch_board_snapshot",
        lambda ctx: _make_snapshot(),
    )
    run_kanpan(temp_mng_ctx)  # type: ignore[arg-type]


# =============================================================================
# Tests for _push_focused_agent with work_dir (executor path)
# =============================================================================


def test_push_focused_agent_with_work_dir_starts_push(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "imbue.mng_kanpan.tui._run_git_push",
        lambda work_dir: subprocess.CompletedProcess(args=[], returncode=0),
    )
    entries = (_make_entry(name="local-agent", work_dir=Path("/tmp/work")),)
    state = _make_state(snapshot=_make_snapshot(entries=entries))
    walker = _build_board_widgets(state)
    state.list_walker = walker
    agent_idx = next(iter(state.index_to_entry.keys()))
    walker.set_focus(agent_idx)
    _push_focused_agent(state)
    assert state.pushing_agent_name == AgentName("local-agent")
    assert "Pushing local-agent" in state.footer_left_text.get_text()[0]
    assert state.executor is not None
    state.executor.shutdown(wait=True)


# =============================================================================
# Tests for _dispatch_command refresh with loop
# =============================================================================


def test_dispatch_command_refresh_with_loop_starts_refresh(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "imbue.mng_kanpan.tui.fetch_board_snapshot",
        lambda ctx: _make_snapshot(),
    )
    state = _make_state()
    state.loop = MagicMock()
    cmd = CustomCommand(name="refresh")
    _dispatch_command(state, "r", cmd)
    assert state.refresh_future is not None
    assert state.executor is not None
    state.executor.shutdown(wait=True)


# =============================================================================
# Tests for _show_transient_message with loop
# =============================================================================


def test_show_transient_message_with_loop_schedules_alarm() -> None:
    state = _make_state()
    state.loop = MagicMock()
    _show_transient_message(state, "  Test message")
    state.loop.set_alarm_in.assert_called_once()


# =============================================================================
# Tests for _load_user_commands with dict values (model_construct path)
# =============================================================================


def test_load_user_commands_handles_dict_values() -> None:
    mng_ctx = MagicMock()
    config = KanpanPluginConfig.model_construct(
        enabled=True,
        commands={"x": {"name": "from-dict", "command": "echo hi"}},
    )
    mng_ctx.config.plugins = {PluginName("kanpan"): config}
    commands = _load_user_commands(mng_ctx)
    assert "x" in commands
    assert commands["x"].name == "from-dict"
