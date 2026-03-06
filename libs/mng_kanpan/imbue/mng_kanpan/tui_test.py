import time
from collections.abc import Callable
from concurrent.futures import Future
from types import SimpleNamespace
from typing import Any

from urwid.event_loop.main_loop import MainLoop
from urwid.widget.attr_map import AttrMap
from urwid.widget.columns import Columns
from urwid.widget.text import Text

from imbue.mng.primitives import AgentLifecycleState
from imbue.mng.primitives import AgentName
from imbue.mng.primitives import ProviderInstanceName
from imbue.mng_kanpan.data_types import AgentBoardEntry
from imbue.mng_kanpan.data_types import BoardSnapshot
from imbue.mng_kanpan.testing import make_pr_info
from imbue.mng_kanpan.tui import DEFAULT_REFRESH_INTERVAL_SECONDS
from imbue.mng_kanpan.tui import _KanpanState
from imbue.mng_kanpan.tui import _build_board_widgets
from imbue.mng_kanpan.tui import _carry_forward_pr_data
from imbue.mng_kanpan.tui import _finish_refresh
from imbue.mng_kanpan.tui import _request_refresh
from imbue.mng_kanpan.tui import _start_local_refresh


def _text_from_widget(widget: Text) -> str:
    """Extract plain text content from a single Text widget."""
    raw = widget.text
    if isinstance(raw, str):
        return raw
    parts: list[str] = []
    for seg in raw:
        if isinstance(seg, tuple):
            parts.append(str(seg[1]))
        else:
            parts.append(str(seg))
    return "".join(parts)


def _extract_text(walker: list[object]) -> list[str]:
    """Extract plain text from all Text and Columns widgets in a walker."""
    texts: list[str] = []
    for widget in walker:
        inner = widget.original_widget if isinstance(widget, AttrMap) else widget
        if isinstance(inner, Text):
            texts.append(_text_from_widget(inner))
        elif isinstance(inner, Columns):
            cell_texts = [_text_from_widget(child) for child, _options in inner.contents if isinstance(child, Text)]
            texts.append(" ".join(cell_texts))
    return texts


def _text_contains(texts: list[str], substring: str) -> bool:
    return any(substring in t for t in texts)


# === _carry_forward_pr_data ===


def test_carry_forward_pr_data_preserves_old_prs() -> None:
    pr = make_pr_info(number=42, head_branch="mng/agent-1")
    old_entry = AgentBoardEntry(
        name=AgentName("agent-1"),
        state=AgentLifecycleState.RUNNING,
        provider_name=ProviderInstanceName("modal"),
        branch="mng/agent-1",
        pr=pr,
        create_pr_url=None,
    )
    old = BoardSnapshot(entries=(old_entry,), prs_loaded=True, fetch_time_seconds=1.0)

    new_entry = AgentBoardEntry(
        name=AgentName("agent-1"),
        state=AgentLifecycleState.RUNNING,
        provider_name=ProviderInstanceName("modal"),
        branch="mng/agent-1",
        pr=None,
        create_pr_url=None,
    )
    new = BoardSnapshot(
        entries=(new_entry,),
        errors=("gh auth failed",),
        prs_loaded=False,
        fetch_time_seconds=2.0,
    )

    result = _carry_forward_pr_data(old, new)
    assert result.prs_loaded is True
    assert result.entries[0].pr is not None
    assert result.entries[0].pr.number == 42
    assert "gh auth failed" in result.errors[0]
    assert result.fetch_time_seconds == 2.0


def test_carry_forward_pr_data_preserves_create_pr_url_without_pr() -> None:
    """When the old snapshot has a create_pr_url but no PR, it should be carried forward."""
    old_entry = AgentBoardEntry(
        name=AgentName("agent-1"),
        state=AgentLifecycleState.RUNNING,
        provider_name=ProviderInstanceName("modal"),
        branch="mng/agent-1",
        pr=None,
        create_pr_url="https://github.com/org/repo/compare/mng/agent-1?expand=1",
    )
    old = BoardSnapshot(entries=(old_entry,), prs_loaded=True, fetch_time_seconds=1.0)

    new_entry = AgentBoardEntry(
        name=AgentName("agent-1"),
        state=AgentLifecycleState.RUNNING,
        provider_name=ProviderInstanceName("modal"),
        branch="mng/agent-1",
        pr=None,
        create_pr_url=None,
    )
    new = BoardSnapshot(entries=(new_entry,), prs_loaded=False, fetch_time_seconds=2.0)

    result = _carry_forward_pr_data(old, new)
    assert result.prs_loaded is True
    assert result.entries[0].pr is None
    assert result.entries[0].create_pr_url == "https://github.com/org/repo/compare/mng/agent-1?expand=1"


def test_carry_forward_pr_data_handles_new_agents() -> None:
    """New agents that weren't in the old snapshot get no PR data carried forward."""
    old = BoardSnapshot(entries=(), prs_loaded=True, fetch_time_seconds=1.0)

    new_entry = AgentBoardEntry(
        name=AgentName("agent-new"),
        state=AgentLifecycleState.RUNNING,
        provider_name=ProviderInstanceName("modal"),
        branch="mng/agent-new",
    )
    new = BoardSnapshot(entries=(new_entry,), prs_loaded=False, fetch_time_seconds=2.0)

    result = _carry_forward_pr_data(old, new)
    assert result.entries[0].pr is None


# === _build_board_widgets: first-load PR failure ===


def test_first_load_pr_failure_shows_prs_not_loaded() -> None:
    """When the first load fails to fetch PRs, the heading should say 'PRs not loaded'
    and no create-PR links should appear."""
    entry = AgentBoardEntry(
        name=AgentName("agent-1"),
        state=AgentLifecycleState.RUNNING,
        provider_name=ProviderInstanceName("modal"),
        branch="mng/agent-1",
        pr=None,
        create_pr_url=None,
    )
    snapshot = BoardSnapshot(
        entries=(entry,),
        errors=("gh pr list failed: auth required",),
        prs_loaded=False,
        fetch_time_seconds=1.0,
    )
    walker, _ = _build_board_widgets(snapshot)

    texts = _extract_text(list(walker))
    assert _text_contains(texts, "PRs not loaded")
    assert not _text_contains(texts, "no PR yet")
    assert not _text_contains(texts, "create PR")
    assert _text_contains(texts, "gh pr list failed")


def test_first_load_pr_success_shows_normal_heading() -> None:
    """When PRs load successfully, agents without PRs show normal 'no PR yet' heading."""
    entry = AgentBoardEntry(
        name=AgentName("agent-1"),
        state=AgentLifecycleState.RUNNING,
        provider_name=ProviderInstanceName("modal"),
        branch="mng/agent-1",
        pr=None,
        create_pr_url="https://github.com/org/repo/compare/mng/agent-1?expand=1",
    )
    snapshot = BoardSnapshot(
        entries=(entry,),
        prs_loaded=True,
        fetch_time_seconds=1.0,
    )
    walker, _ = _build_board_widgets(snapshot)

    texts = _extract_text(list(walker))
    assert _text_contains(texts, "no PR yet")
    assert not _text_contains(texts, "PRs not loaded")


def test_second_load_pr_failure_shows_carried_forward_prs() -> None:
    """When the second load fails to fetch PRs, carry-forward preserves PR data
    and the TUI shows normal PR info (not 'PRs not loaded')."""
    pr = make_pr_info(number=42, head_branch="mng/agent-1")
    old_entry = AgentBoardEntry(
        name=AgentName("agent-1"),
        state=AgentLifecycleState.RUNNING,
        provider_name=ProviderInstanceName("modal"),
        branch="mng/agent-1",
        pr=pr,
        create_pr_url=None,
    )
    old = BoardSnapshot(entries=(old_entry,), prs_loaded=True, fetch_time_seconds=1.0)

    new_entry = AgentBoardEntry(
        name=AgentName("agent-1"),
        state=AgentLifecycleState.RUNNING,
        provider_name=ProviderInstanceName("modal"),
        branch="mng/agent-1",
        pr=None,
        create_pr_url=None,
    )
    new = BoardSnapshot(
        entries=(new_entry,),
        errors=("gh pr list failed: network error",),
        prs_loaded=False,
        fetch_time_seconds=2.0,
    )

    carried = _carry_forward_pr_data(old, new)
    walker, _ = _build_board_widgets(carried)

    texts = _extract_text(list(walker))
    assert _text_contains(texts, "github.com/org/repo/pull/42")
    assert not _text_contains(texts, "PRs not loaded")
    assert not _text_contains(texts, "no PR yet")
    assert not _text_contains(texts, "create PR")
    assert _text_contains(texts, "network error")


# === Debounce / refresh tests ===


class _AlarmRecord(SimpleNamespace):
    """Record of a set_alarm_in call."""

    delay: float
    callback: object
    user_data: object


class _TestableLoop(MainLoop):
    """MainLoop subclass that records alarm operations instead of registering with the event loop."""

    def __init__(self) -> None:
        super().__init__(Text(""))
        self.alarms: list[_AlarmRecord] = []
        self.removed_alarms: list[object] = []
        self._next_handle = 0

    def set_alarm_in(self, sec: float, callback: Callable[..., Any], user_data: Any = None) -> int:
        handle = self._next_handle
        self._next_handle += 1
        self.alarms.append(_AlarmRecord(delay=sec, callback=callback, user_data=user_data))
        return handle

    def remove_alarm(self, handle: object) -> bool:
        self.removed_alarms.append(handle)
        return True


class _FakeExecutor:
    """Executor whose submit() always returns a pre-built future."""

    def __init__(self, future: Future[BoardSnapshot]) -> None:
        self._future = future

    def submit(self, fn: object, *args: object, **kwargs: object) -> Future[BoardSnapshot]:
        return self._future


def _make_dummy_snapshot(**overrides: Any) -> BoardSnapshot:
    """Build a BoardSnapshot with a single dummy entry to avoid empty-entries edge cases."""
    defaults: dict[str, Any] = {
        "entries": (
            AgentBoardEntry(
                name=AgentName("dummy"),
                state=AgentLifecycleState.DONE,
                provider_name=ProviderInstanceName("modal"),
            ),
        ),
        "fetch_time_seconds": 0.1,
    }
    defaults.update(overrides)
    return BoardSnapshot(**defaults)


def _make_state(**overrides: Any) -> _KanpanState:
    """Build a _KanpanState with fake urwid widgets and sensible defaults."""
    defaults: dict[str, Any] = {
        "mng_ctx": SimpleNamespace(config=SimpleNamespace(plugins={})),
        "frame": SimpleNamespace(body=None),
        "footer_left_text": SimpleNamespace(set_text=lambda text: None),
        "footer_left_attr": SimpleNamespace(set_attr_map=lambda m: None),
        "footer_right": SimpleNamespace(set_text=lambda text: None),
    }
    defaults.update(overrides)
    return _KanpanState.model_construct(**defaults)


def test_request_refresh_starts_immediately_when_cooldown_expired() -> None:
    loop = _TestableLoop()
    pre_built_future: Future[BoardSnapshot] = Future()
    pre_built_future.set_result(_make_dummy_snapshot())
    executor = _FakeExecutor(pre_built_future)
    state = _make_state(
        last_refresh_time=time.monotonic() - 100,
        executor=executor,
    )

    _request_refresh(loop, state, cooldown_seconds=5.0)

    assert state.refresh_future is pre_built_future


def test_request_refresh_defers_when_within_cooldown() -> None:
    loop = _TestableLoop()
    state = _make_state(last_refresh_time=time.monotonic())

    _request_refresh(loop, state, cooldown_seconds=60.0)

    assert state.refresh_future is None
    assert state.deferred_refresh_alarm is not None
    assert len(loop.alarms) == 1
    delay = loop.alarms[0].delay
    assert 59.0 < delay <= 60.0


def test_request_refresh_replaces_deferred_with_sooner_alarm() -> None:
    """A manual refresh (short cooldown) should replace a pending auto refresh (long cooldown)."""
    loop = _TestableLoop()
    now = time.monotonic()
    state = _make_state(
        last_refresh_time=now - 2,
        deferred_refresh_alarm=999,
        deferred_refresh_fire_at=now + 58,
    )

    _request_refresh(loop, state, cooldown_seconds=5.0)

    assert 999 in loop.removed_alarms
    assert state.deferred_refresh_alarm is not None
    assert len(loop.alarms) == 1
    delay = loop.alarms[0].delay
    assert 2.0 < delay <= 3.0


def test_request_refresh_keeps_existing_if_sooner() -> None:
    """An auto refresh request should not replace a sooner pending manual refresh."""
    loop = _TestableLoop()
    now = time.monotonic()
    state = _make_state(
        last_refresh_time=now - 2,
        deferred_refresh_alarm=777,
        deferred_refresh_fire_at=now + 3,
    )

    _request_refresh(loop, state, cooldown_seconds=60.0)

    assert len(loop.removed_alarms) == 0
    assert len(loop.alarms) == 0
    assert state.deferred_refresh_alarm == 777


def test_request_refresh_noop_when_already_refreshing() -> None:
    loop = _TestableLoop()
    existing_future: Future[BoardSnapshot] = Future()
    state = _make_state(refresh_future=existing_future)

    _request_refresh(loop, state, cooldown_seconds=0.0)

    assert state.refresh_future is existing_future
    assert len(loop.alarms) == 0


def test_finish_refresh_schedules_normal_interval_on_success() -> None:
    loop = _TestableLoop()
    snapshot = _make_dummy_snapshot(fetch_time_seconds=1.0)
    future: Future[BoardSnapshot] = Future()
    future.set_result(snapshot)
    state = _make_state(refresh_future=future)

    _finish_refresh(loop, state)

    assert state.snapshot == snapshot
    assert state.refresh_future is None
    auto_refresh_alarms = [a for a in loop.alarms if a.delay == DEFAULT_REFRESH_INTERVAL_SECONDS]
    assert len(auto_refresh_alarms) == 1


def test_finish_refresh_uses_auto_cooldown_on_failure() -> None:
    """After a failed refresh, the next refresh should be deferred by retry_cooldown_seconds."""
    loop = _TestableLoop()
    future: Future[BoardSnapshot] = Future()
    future.set_exception(RuntimeError("GitHub API error"))
    state = _make_state(
        refresh_future=future,
        retry_cooldown_seconds=30.0,
    )

    _finish_refresh(loop, state)

    assert state.refresh_future is None
    assert state.deferred_refresh_alarm is not None
    assert len(loop.alarms) == 1
    delay = loop.alarms[0].delay
    assert 29.0 < delay <= 30.0


# === local-only refresh ===


def test_local_refresh_does_not_reset_last_refresh_time() -> None:
    """A local-only refresh should not update last_refresh_time."""
    loop = _TestableLoop()
    snapshot = _make_dummy_snapshot(prs_loaded=False)
    future: Future[BoardSnapshot] = Future()
    future.set_result(snapshot)
    original_time = 1000.0
    state = _make_state(
        refresh_future=future,
        refresh_is_local_only=True,
        last_refresh_time=original_time,
    )

    _finish_refresh(loop, state)

    assert state.last_refresh_time == original_time
    assert state.refresh_future is None
    assert state.refresh_is_local_only is False


def test_local_refresh_does_not_schedule_next_auto_refresh() -> None:
    """A local-only refresh should not schedule the next periodic auto-refresh."""
    loop = _TestableLoop()
    snapshot = _make_dummy_snapshot(prs_loaded=False)
    future: Future[BoardSnapshot] = Future()
    future.set_result(snapshot)
    state = _make_state(
        refresh_future=future,
        refresh_is_local_only=True,
    )

    _finish_refresh(loop, state)

    auto_refresh_alarms = [a for a in loop.alarms if a.delay == DEFAULT_REFRESH_INTERVAL_SECONDS]
    assert len(auto_refresh_alarms) == 0


def test_start_local_refresh_noop_when_already_refreshing() -> None:
    """_start_local_refresh should do nothing if a refresh is already in flight."""
    loop = _TestableLoop()
    existing_future: Future[BoardSnapshot] = Future()
    state = _make_state(refresh_future=existing_future)

    _start_local_refresh(loop, state)

    assert state.refresh_future is existing_future
    assert len(loop.alarms) == 0
