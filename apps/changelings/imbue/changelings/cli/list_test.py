from typing import Any

from click.testing import CliRunner

from imbue.changelings.cli.list import _DEFAULT_DISPLAY_FIELDS
from imbue.changelings.cli.list import _build_table
from imbue.changelings.cli.list import _get_field_value
from imbue.changelings.main import cli

_RUNNER = CliRunner()


def _make_agent_dict(
    agent_id: str,
    name: str = "test-agent",
    state: str = "RUNNING",
    host_state: str = "RUNNING",
    provider: str = "local",
) -> dict[str, Any]:
    """Create a mock mng agent dict."""
    return {
        "id": agent_id,
        "name": name,
        "state": state,
        "host": {
            "name": "@local",
            "state": host_state,
            "provider_name": provider,
        },
    }


# --- _get_field_value tests ---


def test_get_field_value_simple() -> None:
    agent = {"name": "my-agent", "state": "RUNNING"}

    assert _get_field_value(agent, "name") == "my-agent"
    assert _get_field_value(agent, "state") == "RUNNING"


def test_get_field_value_nested() -> None:
    agent = {"host": {"name": "@local", "state": "RUNNING"}}

    assert _get_field_value(agent, "host.name") == "@local"
    assert _get_field_value(agent, "host.state") == "RUNNING"


def test_get_field_value_missing() -> None:
    agent = {"name": "my-agent"}

    assert _get_field_value(agent, "state") == ""
    assert _get_field_value(agent, "host.name") == ""


# --- _build_table tests ---


def test_build_table_single_agent() -> None:
    """Verify that _build_table builds a row from agent data."""
    agents = [_make_agent_dict("agent-abc123", name="my-bot", state="RUNNING")]

    rows = _build_table(agents, _DEFAULT_DISPLAY_FIELDS)

    assert len(rows) == 1
    row = rows[0]
    # name, id, state, host.provider_name, host.state
    assert row[0] == "my-bot"
    assert row[1] == "agent-abc123"
    assert row[2] == "RUNNING"
    assert row[3] == "local"
    assert row[4] == "RUNNING"


def test_build_table_multiple_agents() -> None:
    """Verify that _build_table handles multiple agents."""
    agents = [
        _make_agent_dict("agent-aaa", name="bot-1", state="RUNNING"),
        _make_agent_dict("agent-bbb", name="bot-2", state="STOPPED"),
    ]

    rows = _build_table(agents, _DEFAULT_DISPLAY_FIELDS)

    assert len(rows) == 2
    assert rows[0][0] == "bot-1"
    assert rows[1][0] == "bot-2"


def test_build_table_empty() -> None:
    """Verify that _build_table returns empty list for no agents."""
    rows = _build_table([], _DEFAULT_DISPLAY_FIELDS)

    assert rows == []


def test_build_table_shows_provider() -> None:
    """Verify that _build_table includes provider info."""
    agents = [_make_agent_dict("agent-abc", name="remote-bot", provider="modal")]

    rows = _build_table(agents, _DEFAULT_DISPLAY_FIELDS)

    assert len(rows) == 1
    # host.provider_name is the 4th field in _DEFAULT_DISPLAY_FIELDS
    assert rows[0][3] == "modal"


# --- CLI tests ---


def test_list_help() -> None:
    """Verify that changeling list --help works."""
    result = _RUNNER.invoke(cli, ["list", "--help"])

    assert result.exit_code == 0
    assert "List deployed changelings" in result.output
