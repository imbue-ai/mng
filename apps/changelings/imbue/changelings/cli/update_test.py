import json
from collections.abc import Callable
from collections.abc import Mapping
from collections.abc import Sequence
from pathlib import Path

from click.testing import CliRunner

from imbue.changelings.cli.update import _is_agent_remote
from imbue.changelings.main import cli
from imbue.changelings.primitives import AgentName
from imbue.concurrency_group.concurrency_group import ConcurrencyGroup
from imbue.concurrency_group.event_utils import ReadOnlyEvent
from imbue.concurrency_group.subprocess_utils import FinishedProcess

_RUNNER = CliRunner()


def _make_finished_process(
    returncode: int = 0,
    stdout: str = "",
    stderr: str = "",
    command: tuple[str, ...] = ("mng",),
) -> FinishedProcess:
    return FinishedProcess(
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
        command=command,
        is_output_already_logged=False,
    )


class _FakeRemoteCheckCG(ConcurrencyGroup):
    """ConcurrencyGroup that returns a pre-configured mng list result."""

    _result: FinishedProcess

    def __init__(self, result: FinishedProcess) -> None:
        super().__init__(name="fake-remote-check")
        self._result = result

    def run_process_to_completion(
        self,
        command: Sequence[str],
        timeout: float | None = None,
        is_checked_after: bool = True,
        on_output: Callable[[str, bool], None] | None = None,
        cwd: Path | None = None,
        env: Mapping[str, str] | None = None,
        shutdown_event: ReadOnlyEvent | None = None,
    ) -> FinishedProcess:
        return self._result


def _make_list_result(provider: str) -> FinishedProcess:
    """Create a FinishedProcess with mng list JSON output for the given provider."""
    return _make_finished_process(
        stdout=json.dumps(
            {
                "agents": [
                    {
                        "id": "agent-abc123",
                        "name": "my-agent",
                        "host": {"provider": provider, "state": "RUNNING"},
                    }
                ]
            }
        ),
        command=("mng", "list"),
    )


def test_update_requires_agent_name() -> None:
    result = _RUNNER.invoke(cli, ["update"])

    assert result.exit_code != 0
    assert "Missing argument" in result.output


def test_update_help_shows_flags() -> None:
    result = _RUNNER.invoke(cli, ["update", "--help"])

    assert result.exit_code == 0
    assert "--snapshot" in result.output
    assert "--no-snapshot" in result.output
    assert "--push" in result.output
    assert "--no-push" in result.output
    assert "--provision" in result.output
    assert "--no-provision" in result.output


def test_update_help_describes_steps() -> None:
    result = _RUNNER.invoke(cli, ["update", "--help"])

    assert result.exit_code == 0
    assert "snapshot" in result.output.lower()
    assert "AGENT_NAME" in result.output


def test_update_shows_in_cli_help() -> None:
    result = _RUNNER.invoke(cli, ["--help"])

    assert result.exit_code == 0
    assert "update" in result.output


# --- _is_agent_remote tests ---


def test_is_agent_remote_returns_false_for_local() -> None:
    """Verify _is_agent_remote returns False for a local agent."""
    cg = _FakeRemoteCheckCG(_make_list_result("local"))

    assert _is_agent_remote(AgentName("my-agent"), concurrency_group=cg) is False


def test_is_agent_remote_returns_true_for_modal() -> None:
    """Verify _is_agent_remote returns True for a modal agent."""
    cg = _FakeRemoteCheckCG(_make_list_result("modal"))

    assert _is_agent_remote(AgentName("my-agent"), concurrency_group=cg) is True


def test_is_agent_remote_returns_true_for_docker() -> None:
    """Verify _is_agent_remote returns True for a docker agent."""
    cg = _FakeRemoteCheckCG(_make_list_result("docker"))

    assert _is_agent_remote(AgentName("my-agent"), concurrency_group=cg) is True


def test_is_agent_remote_returns_false_on_failure() -> None:
    """Verify _is_agent_remote returns False when the check fails (fail-open)."""
    cg = _FakeRemoteCheckCG(_make_finished_process(returncode=1, stderr="error", command=("mng", "list")))

    assert _is_agent_remote(AgentName("my-agent"), concurrency_group=cg) is False


def test_is_agent_remote_returns_false_on_invalid_json() -> None:
    """Verify _is_agent_remote returns False when JSON parsing fails."""
    cg = _FakeRemoteCheckCG(_make_finished_process(stdout="not valid json {{{", command=("mng", "list")))

    assert _is_agent_remote(AgentName("my-agent"), concurrency_group=cg) is False


def test_is_agent_remote_returns_false_when_agent_not_found() -> None:
    """Verify _is_agent_remote returns False when no agents match."""
    cg = _FakeRemoteCheckCG(
        _make_finished_process(
            stdout=json.dumps({"agents": []}),
            command=("mng", "list"),
        )
    )

    assert _is_agent_remote(AgentName("ghost"), concurrency_group=cg) is False
