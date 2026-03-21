from imbue.mng.config.data_types import OutputOptions
from imbue.mng.primitives import AgentLifecycleState
from imbue.mng.primitives import HostState
from imbue.mng.primitives import OutputFormat
from imbue.mng_wait.cli import _emit_state_change
from imbue.mng_wait.cli import _output_result
from imbue.mng_wait.data_types import StateChange
from imbue.mng_wait.data_types import StateSnapshot
from imbue.mng_wait.data_types import WaitResult
from imbue.mng_wait.data_types import WaitTarget
from imbue.mng_wait.primitives import WaitTargetType


def _make_matched_result() -> WaitResult:
    return WaitResult(
        target=WaitTarget(identifier="test-agent", target_type=WaitTargetType.AGENT),
        is_matched=True,
        is_timed_out=False,
        final_snapshot=StateSnapshot(
            host_state=HostState.RUNNING,
            agent_state=AgentLifecycleState.DONE,
        ),
        matched_state="DONE",
        elapsed_seconds=5.0,
        state_changes=(),
    )


def _make_timed_out_result() -> WaitResult:
    return WaitResult(
        target=WaitTarget(identifier="test-agent", target_type=WaitTargetType.AGENT),
        is_matched=False,
        is_timed_out=True,
        final_snapshot=StateSnapshot(
            host_state=HostState.RUNNING,
            agent_state=AgentLifecycleState.RUNNING,
        ),
        matched_state=None,
        elapsed_seconds=30.0,
        state_changes=(),
    )


def test_emit_state_change_human_format() -> None:
    change = StateChange(
        field="agent_state",
        old_value="RUNNING",
        new_value="WAITING",
        elapsed_seconds=5.0,
    )
    _emit_state_change(change, OutputFormat.HUMAN)


def test_emit_state_change_jsonl_format() -> None:
    change = StateChange(
        field="host_state",
        old_value="RUNNING",
        new_value="STOPPED",
        elapsed_seconds=10.0,
    )
    _emit_state_change(change, OutputFormat.JSONL)


def test_emit_state_change_json_format_is_silent() -> None:
    change = StateChange(
        field="agent_state",
        old_value="RUNNING",
        new_value="DONE",
        elapsed_seconds=3.0,
    )
    _emit_state_change(change, OutputFormat.JSON)


def test_output_result_matched_human() -> None:
    result = _make_matched_result()
    output_opts = OutputOptions(
        output_format=OutputFormat.HUMAN,
        format_template=None,
        is_quiet=False,
    )
    _output_result(result, output_opts)


def test_output_result_timed_out_human() -> None:
    result = _make_timed_out_result()
    output_opts = OutputOptions(
        output_format=OutputFormat.HUMAN,
        format_template=None,
        is_quiet=False,
    )
    _output_result(result, output_opts)


def test_output_result_json_format() -> None:
    result = _make_matched_result()
    output_opts = OutputOptions(
        output_format=OutputFormat.JSON,
        format_template=None,
        is_quiet=False,
    )
    _output_result(result, output_opts)


def test_output_result_jsonl_format() -> None:
    result = _make_matched_result()
    output_opts = OutputOptions(
        output_format=OutputFormat.JSONL,
        format_template=None,
        is_quiet=False,
    )
    _output_result(result, output_opts)


def test_output_result_unmatched_not_timed_out() -> None:
    result = WaitResult(
        target=WaitTarget(identifier="test-host", target_type=WaitTargetType.HOST),
        is_matched=False,
        is_timed_out=False,
        final_snapshot=StateSnapshot(host_state=HostState.RUNNING),
        matched_state=None,
        elapsed_seconds=2.0,
        state_changes=(),
    )
    output_opts = OutputOptions(
        output_format=OutputFormat.HUMAN,
        format_template=None,
        is_quiet=False,
    )
    _output_result(result, output_opts)
