import json

from imbue.mngr.api.enforce import EnforceAction
from imbue.mngr.api.enforce import EnforceResult
from imbue.mngr.cli.enforce import _emit_human_summary
from imbue.mngr.cli.enforce import _emit_jsonl_summary
from imbue.mngr.cli.enforce import _format_action_message
from imbue.mngr.primitives import HostId
from imbue.mngr.primitives import HostState
from imbue.mngr.primitives import ProviderInstanceName

# =============================================================================
# Helper for creating test data
# =============================================================================


def _create_enforce_action(
    host_name: str = "test-host",
    provider_name: str = "docker",
    host_state: HostState = HostState.RUNNING,
    action: str = "stop_host",
    reason: str = "Idle timeout exceeded",
    is_dry_run: bool = False,
) -> EnforceAction:
    """Create an EnforceAction for testing."""
    return EnforceAction(
        host_id=HostId.generate(),
        host_name=host_name,
        provider_name=ProviderInstanceName(provider_name),
        host_state=host_state,
        action=action,
        reason=reason,
        is_dry_run=is_dry_run,
    )


# =============================================================================
# Tests for _format_action_message
# =============================================================================


def test_format_action_message_stop_executed() -> None:
    """_format_action_message should format executed stop messages."""
    action = _create_enforce_action(
        host_name="my-host",
        provider_name="docker",
        action="stop_host",
        reason="Host idle for 3700s, exceeding timeout of 3600s",
        is_dry_run=False,
    )
    msg = _format_action_message(action)
    assert msg == "Executed stop my-host (docker): Host idle for 3700s, exceeding timeout of 3600s"


def test_format_action_message_stop_dry_run() -> None:
    """_format_action_message should format dry-run stop messages."""
    action = _create_enforce_action(
        host_name="my-host",
        provider_name="docker",
        action="stop_host",
        reason="Host idle for 3700s, exceeding timeout of 3600s",
        is_dry_run=True,
    )
    msg = _format_action_message(action)
    assert msg == "Would stop my-host (docker): Host idle for 3700s, exceeding timeout of 3600s"


def test_format_action_message_destroy() -> None:
    """_format_action_message should format destroy messages."""
    action = _create_enforce_action(
        host_name="stuck-host",
        provider_name="modal",
        action="destroy_host",
        reason="Host stuck in STOPPING for 700s",
        is_dry_run=False,
    )
    msg = _format_action_message(action)
    assert msg == "Executed destroy stuck-host (modal): Host stuck in STOPPING for 700s"


def test_format_action_message_destroy_dry_run() -> None:
    """_format_action_message should format dry-run destroy messages."""
    action = _create_enforce_action(
        host_name="stuck-host",
        provider_name="modal",
        action="destroy_host",
        reason="Host stuck in STOPPING for 700s",
        is_dry_run=True,
    )
    msg = _format_action_message(action)
    assert msg == "Would destroy stuck-host (modal): Host stuck in STOPPING for 700s"


# =============================================================================
# Tests for _emit_jsonl_summary
# =============================================================================


def test_emit_jsonl_summary_empty_result(capsys) -> None:
    """_emit_jsonl_summary should output correct totals for empty result."""
    result = EnforceResult()
    _emit_jsonl_summary(result, is_dry_run=False)

    captured = capsys.readouterr()
    output = json.loads(captured.out.strip())

    assert output["event"] == "summary"
    assert output["hosts_checked"] == 0
    assert output["idle_violations"] == 0
    assert output["timeout_violations"] == 0
    assert output["total_actions"] == 0
    assert output["errors_count"] == 0
    assert output["dry_run"] is False


def test_emit_jsonl_summary_with_actions(capsys) -> None:
    """_emit_jsonl_summary should count actions correctly."""
    result = EnforceResult()
    result.hosts_checked = 5
    result.idle_violations = 2
    result.timeout_violations = 1
    result.actions = [
        _create_enforce_action(action="stop_host"),
        _create_enforce_action(action="stop_host"),
        _create_enforce_action(action="destroy_host", host_state=HostState.STOPPING),
    ]

    _emit_jsonl_summary(result, is_dry_run=True)

    captured = capsys.readouterr()
    output = json.loads(captured.out.strip())

    assert output["hosts_checked"] == 5
    assert output["idle_violations"] == 2
    assert output["timeout_violations"] == 1
    assert output["total_actions"] == 3
    assert output["dry_run"] is True


def test_emit_jsonl_summary_with_errors(capsys) -> None:
    """_emit_jsonl_summary should include errors in output."""
    result = EnforceResult()
    result.errors = ["Failed to check host: connection error", "Provider auth failed"]

    _emit_jsonl_summary(result, is_dry_run=False)

    captured = capsys.readouterr()
    output = json.loads(captured.out.strip())

    assert output["errors_count"] == 2
    assert output["errors"] == ["Failed to check host: connection error", "Provider auth failed"]


# =============================================================================
# Tests for _emit_human_summary
# =============================================================================


def test_emit_human_summary_empty_result() -> None:
    """_emit_human_summary should indicate no actions needed for empty result."""
    result = EnforceResult()
    # Just verify no exception is raised; output goes to logger
    _emit_human_summary(result, is_dry_run=False)


def test_emit_human_summary_dry_run() -> None:
    """_emit_human_summary should indicate dry run mode."""
    result = EnforceResult()
    result.hosts_checked = 3
    result.actions = [_create_enforce_action(is_dry_run=True)]
    result.idle_violations = 1
    # Just verify no exception is raised
    _emit_human_summary(result, is_dry_run=True)


def test_emit_human_summary_with_actions() -> None:
    """_emit_human_summary should count actions correctly."""
    result = EnforceResult()
    result.hosts_checked = 10
    result.idle_violations = 2
    result.timeout_violations = 1
    result.actions = [
        _create_enforce_action(),
        _create_enforce_action(),
        _create_enforce_action(host_state=HostState.STOPPING, action="destroy_host"),
    ]
    # Just verify no exception is raised
    _emit_human_summary(result, is_dry_run=False)


def test_emit_human_summary_with_errors() -> None:
    """_emit_human_summary should display errors."""
    result = EnforceResult()
    result.errors = ["Failed to check host: timeout"]
    _emit_human_summary(result, is_dry_run=False)
