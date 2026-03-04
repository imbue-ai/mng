"""Unit tests for the tutor TUI."""

from typing import Any
from unittest.mock import MagicMock

import pytest
from urwid.event_loop.abstract_loop import ExitMainLoop
from urwid.widget.attr_map import AttrMap
from urwid.widget.listbox import SimpleFocusListWalker
from urwid.widget.text import Text
from urwid.widget.wimp import SelectableIcon

from imbue.mng.primitives import AgentName
from imbue.mng_tutor.data_types import AgentExistsCheck
from imbue.mng_tutor.data_types import Lesson
from imbue.mng_tutor.data_types import LessonStep
from imbue.mng_tutor.tui import _LessonRunnerInputHandler
from imbue.mng_tutor.tui import _LessonRunnerState
from imbue.mng_tutor.tui import _LessonSelectorInputHandler
from imbue.mng_tutor.tui import _LessonSelectorState
from imbue.mng_tutor.tui import _build_step_widgets
from imbue.mng_tutor.tui import _get_current_step_index
from imbue.mng_tutor.tui import _on_check_alarm
from imbue.mng_tutor.tui import _refresh_display
from imbue.mng_tutor.tui import _schedule_next_check
from imbue.mng_tutor.tui import run_lesson_runner
from imbue.mng_tutor.tui import run_lesson_selector

# =============================================================================
# Helpers
# =============================================================================


def _make_step(heading: str = "Step", details: str = "Do something") -> LessonStep:
    return LessonStep(
        heading=heading,
        details=details,
        check=AgentExistsCheck(agent_name=AgentName("test-agent")),
    )


def _make_lesson(
    title: str = "Test Lesson",
    description: str = "A test lesson",
    steps: tuple[LessonStep, ...] | None = None,
) -> Lesson:
    if steps is None:
        steps = (_make_step("Step 1", "First step"), _make_step("Step 2", "Second step"))
    return Lesson(title=title, description=description, steps=steps)


def _make_runner_state(
    lesson: Lesson | None = None,
    step_completed: list[bool] | None = None,
) -> _LessonRunnerState:
    if lesson is None:
        lesson = _make_lesson()
    if step_completed is None:
        step_completed = [False] * len(lesson.steps)
    frame = MagicMock()
    status_text = Text("")
    mng_ctx = MagicMock()
    # Use model_construct to bypass Pydantic validation (MagicMock is not a real MngContext)
    return _LessonRunnerState.model_construct(
        lesson=lesson,
        mng_ctx=mng_ctx,
        step_completed=step_completed,
        frame=frame,
        status_text=status_text,
    )


def _make_selector_handler() -> tuple[_LessonSelectorInputHandler, _LessonSelectorState]:
    """Create a selector handler and its state for testing."""
    lessons = (_make_lesson(),)
    list_walker: SimpleFocusListWalker[AttrMap] = SimpleFocusListWalker([])
    state = _LessonSelectorState(lessons=lessons, list_walker=list_walker)
    handler = _LessonSelectorInputHandler(state=state)
    return handler, state


def _mock_main_loop_factory() -> object:
    """Create a factory that returns a MagicMock MainLoop, ignoring constructor args."""

    def factory(*args: object, **kwargs: object) -> MagicMock:
        return MagicMock()

    return factory


# =============================================================================
# Tests for _get_current_step_index
# =============================================================================


def test_get_current_step_index_all_incomplete() -> None:
    assert _get_current_step_index([False, False, False]) == 0


def test_get_current_step_index_first_complete() -> None:
    assert _get_current_step_index([True, False, False]) == 1


def test_get_current_step_index_all_complete() -> None:
    assert _get_current_step_index([True, True, True]) is None


def test_get_current_step_index_middle_incomplete() -> None:
    assert _get_current_step_index([True, False, True]) == 1


def test_get_current_step_index_empty_list() -> None:
    assert _get_current_step_index([]) is None


# =============================================================================
# Tests for _build_step_widgets
# =============================================================================


def test_build_step_widgets_shows_all_steps() -> None:
    state = _make_runner_state()
    widgets = _build_step_widgets(state)
    text_content = " ".join(str(w.get_text()[0]) for w in widgets if isinstance(w, Text))
    assert "Step 1" in text_content
    assert "Step 2" in text_content


def test_build_step_widgets_current_step_shows_details() -> None:
    state = _make_runner_state()
    widgets = _build_step_widgets(state)
    text_content = " ".join(str(w.get_text()[0]) for w in widgets if isinstance(w, Text))
    assert "First step" in text_content
    # Second step's details should not be shown (not current)
    assert "Second step" not in text_content


def test_build_step_widgets_completed_step_shows_checkmark() -> None:
    state = _make_runner_state(step_completed=[True, False])
    widgets = _build_step_widgets(state)
    text_content = " ".join(str(w.get_text()[0]) for w in widgets if isinstance(w, Text))
    assert "[x]" in text_content
    assert "[ ]" in text_content


def test_build_step_widgets_all_complete_shows_message() -> None:
    state = _make_runner_state(step_completed=[True, True])
    widgets = _build_step_widgets(state)
    text_content = " ".join(str(w.get_text()[0]) for w in widgets if isinstance(w, Text))
    assert "Lesson complete!" in text_content


def test_build_step_widgets_all_complete_has_no_details() -> None:
    state = _make_runner_state(step_completed=[True, True])
    widgets = _build_step_widgets(state)
    text_content = " ".join(str(w.get_text()[0]) for w in widgets if isinstance(w, Text))
    assert "First step" not in text_content
    assert "Second step" not in text_content


# =============================================================================
# Tests for _refresh_display
# =============================================================================


def test_refresh_display_sets_frame_body() -> None:
    state = _make_runner_state()
    _refresh_display(state)
    assert state.frame.body is not None


# =============================================================================
# Tests for _LessonSelectorInputHandler
# =============================================================================


def test_selector_input_handler_q_exits() -> None:
    handler, _ = _make_selector_handler()
    with pytest.raises(ExitMainLoop):
        handler("q")


def test_selector_input_handler_ctrl_c_exits() -> None:
    handler, _ = _make_selector_handler()
    with pytest.raises(ExitMainLoop):
        handler("ctrl c")


def test_selector_input_handler_enter_sets_result_index() -> None:
    lessons = (_make_lesson(title="L1"), _make_lesson(title="L2"))
    items = [
        AttrMap(SelectableIcon(f"  {idx + 1}. {lesson.title}", cursor_position=0), None)
        for idx, lesson in enumerate(lessons)
    ]
    list_walker = SimpleFocusListWalker(items)
    state = _LessonSelectorState(lessons=lessons, list_walker=list_walker)
    handler = _LessonSelectorInputHandler(state=state)

    with pytest.raises(ExitMainLoop):
        handler("enter")
    assert state.result_index == 0


def test_selector_input_handler_arrow_keys_pass_through() -> None:
    handler, _ = _make_selector_handler()
    assert handler("up") is None
    assert handler("down") is None
    assert handler("page up") is None
    assert handler("page down") is None
    assert handler("home") is None
    assert handler("end") is None


def test_selector_input_handler_ignores_mouse_events() -> None:
    handler, state = _make_selector_handler()
    result = handler(("mouse press", 1, 0, 0))
    assert result is None
    assert state.result_index is None


def test_selector_input_handler_swallows_other_keys() -> None:
    handler, state = _make_selector_handler()
    result = handler("x")
    assert result is True
    assert state.result_index is None


# =============================================================================
# Tests for _LessonRunnerInputHandler
# =============================================================================


def test_runner_input_handler_q_exits() -> None:
    handler = _LessonRunnerInputHandler()
    with pytest.raises(ExitMainLoop):
        handler("q")


def test_runner_input_handler_uppercase_q_exits() -> None:
    handler = _LessonRunnerInputHandler()
    with pytest.raises(ExitMainLoop):
        handler("Q")


def test_runner_input_handler_ctrl_c_exits() -> None:
    handler = _LessonRunnerInputHandler()
    with pytest.raises(ExitMainLoop):
        handler("ctrl c")


def test_runner_input_handler_ignores_mouse_events() -> None:
    handler = _LessonRunnerInputHandler()
    result = handler(("mouse press", 1, 0, 0))
    assert result is None


def test_runner_input_handler_swallows_other_keys() -> None:
    handler = _LessonRunnerInputHandler()
    result = handler("x")
    assert result is True


# =============================================================================
# Tests for _schedule_next_check and _on_check_alarm
# =============================================================================


def test_schedule_next_check_sets_alarm() -> None:
    state = _make_runner_state()
    loop = MagicMock()
    _schedule_next_check(loop, state)
    loop.set_alarm_in.assert_called_once()


def test_on_check_alarm_all_complete_sets_status() -> None:
    state = _make_runner_state(step_completed=[True, True])
    loop = MagicMock()
    _on_check_alarm(loop, state)
    status_text = state.status_text.get_text()[0]
    assert "complete" in str(status_text).lower()


def test_on_check_alarm_step_not_passed_schedules_next(monkeypatch: pytest.MonkeyPatch) -> None:
    state = _make_runner_state(step_completed=[False, False])
    monkeypatch.setattr("imbue.mng_tutor.tui.run_check", lambda check, ctx: False)
    loop = MagicMock()
    _on_check_alarm(loop, state)
    loop.set_alarm_in.assert_called_once()
    assert state.step_completed[0] is False


def test_on_check_alarm_step_passed_advances(monkeypatch: pytest.MonkeyPatch) -> None:
    state = _make_runner_state(step_completed=[False, False])
    monkeypatch.setattr("imbue.mng_tutor.tui.run_check", lambda check, ctx: True)
    loop = MagicMock()
    _on_check_alarm(loop, state)
    assert state.step_completed[0] is True
    loop.set_alarm_in.assert_called_once()


def test_on_check_alarm_last_step_passed_shows_complete(monkeypatch: pytest.MonkeyPatch) -> None:
    state = _make_runner_state(step_completed=[True, False])
    monkeypatch.setattr("imbue.mng_tutor.tui.run_check", lambda check, ctx: True)
    loop = MagicMock()
    _on_check_alarm(loop, state)
    assert state.step_completed[1] is True
    status_text = state.status_text.get_text()[0]
    assert "complete" in str(status_text).lower()


# =============================================================================
# Tests for run_lesson_selector and run_lesson_runner (mocked MainLoop)
# =============================================================================


def test_run_lesson_selector_returns_none_on_quit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("imbue.mng_tutor.tui.Screen", lambda: MagicMock())
    monkeypatch.setattr("imbue.mng_tutor.tui.MainLoop", _mock_main_loop_factory())
    lessons = (_make_lesson(title="L1"), _make_lesson(title="L2"))
    result = run_lesson_selector(lessons)
    assert result is None


def test_run_lesson_selector_returns_selected_lesson(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("imbue.mng_tutor.tui.Screen", lambda: MagicMock())

    def fake_main_loop(*args: Any, **kwargs: Any) -> MagicMock:
        loop = MagicMock()
        handler = kwargs.get("unhandled_input") or (args[2] if len(args) > 2 else None)
        if handler is not None:
            handler.state.result_index = 0
        return loop

    monkeypatch.setattr("imbue.mng_tutor.tui.MainLoop", fake_main_loop)
    lessons = (_make_lesson(title="L1"), _make_lesson(title="L2"))
    result = run_lesson_selector(lessons)
    assert result is not None
    assert result.title == "L1"


def test_run_lesson_runner_completes(
    monkeypatch: pytest.MonkeyPatch,
    temp_mng_ctx: Any,
) -> None:
    monkeypatch.setattr("imbue.mng_tutor.tui.Screen", lambda: MagicMock())
    monkeypatch.setattr("imbue.mng_tutor.tui.MainLoop", _mock_main_loop_factory())
    lesson = _make_lesson()
    run_lesson_runner(lesson, temp_mng_ctx)
