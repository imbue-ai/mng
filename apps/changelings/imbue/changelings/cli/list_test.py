import json
from pathlib import Path
from typing import Any

from click.testing import CliRunner

from imbue.changelings.cli.list import _DEFAULT_DISPLAY_FIELDS
from imbue.changelings.cli.list import _build_table
from imbue.changelings.cli.list import _discover_changeling_ids
from imbue.changelings.cli.list import _get_field_value
from imbue.changelings.config.data_types import ChangelingPaths
from imbue.changelings.main import cli
from imbue.mng.primitives import AgentId

_RUNNER = CliRunner()


def _data_dir_args(tmp_path: Path) -> list[str]:
    """Return the --data-dir CLI args pointing to a temp directory."""
    return ["--data-dir", str(tmp_path / "changelings-data")]


def _make_agent_dict(
    agent_id: str,
    name: str = "test-agent",
    state: str = "RUNNING",
    host_state: str = "RUNNING",
) -> dict[str, Any]:
    """Create a mock mng agent dict."""
    return {
        "id": agent_id,
        "name": name,
        "state": state,
        "host": {
            "name": "@local",
            "state": host_state,
            "provider_name": "local",
        },
    }


# --- _discover_changeling_ids tests ---


def test_discover_returns_empty_when_no_data_dir(tmp_path: Path) -> None:
    """Verify that _discover_changeling_ids returns empty when data dir does not exist."""
    paths = ChangelingPaths(data_dir=tmp_path / "nonexistent")

    ids = _discover_changeling_ids(paths)

    assert ids == []


def test_discover_returns_empty_when_no_changeling_dirs(tmp_path: Path) -> None:
    """Verify that _discover_changeling_ids returns empty when data dir has no agent dirs."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    paths = ChangelingPaths(data_dir=data_dir)

    ids = _discover_changeling_ids(paths)

    assert ids == []


def test_discover_finds_agent_directories(tmp_path: Path) -> None:
    """Verify that _discover_changeling_ids finds directories named with agent- prefix."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()

    id1 = AgentId()
    id2 = AgentId()
    (data_dir / str(id1)).mkdir()
    (data_dir / str(id2)).mkdir()

    paths = ChangelingPaths(data_dir=data_dir)
    ids = _discover_changeling_ids(paths)

    assert len(ids) == 2
    id_strs = {str(i) for i in ids}
    assert str(id1) in id_strs
    assert str(id2) in id_strs


def test_discover_skips_hidden_dirs(tmp_path: Path) -> None:
    """Verify that _discover_changeling_ids skips hidden directories."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()

    agent_id = AgentId()
    (data_dir / str(agent_id)).mkdir()
    (data_dir / ".tmp-abc123").mkdir()

    paths = ChangelingPaths(data_dir=data_dir)
    ids = _discover_changeling_ids(paths)

    assert len(ids) == 1
    assert str(ids[0]) == str(agent_id)


def test_discover_skips_auth_dir(tmp_path: Path) -> None:
    """Verify that _discover_changeling_ids skips the auth directory."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()

    agent_id = AgentId()
    (data_dir / str(agent_id)).mkdir()
    (data_dir / "auth").mkdir()

    paths = ChangelingPaths(data_dir=data_dir)
    ids = _discover_changeling_ids(paths)

    assert len(ids) == 1
    assert str(ids[0]) == str(agent_id)


def test_discover_skips_non_agent_dirs(tmp_path: Path) -> None:
    """Verify that _discover_changeling_ids skips dirs without agent- prefix."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()

    agent_id = AgentId()
    (data_dir / str(agent_id)).mkdir()
    (data_dir / "some-other-dir").mkdir()

    paths = ChangelingPaths(data_dir=data_dir)
    ids = _discover_changeling_ids(paths)

    assert len(ids) == 1
    assert str(ids[0]) == str(agent_id)


def test_discover_skips_files(tmp_path: Path) -> None:
    """Verify that _discover_changeling_ids skips regular files."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()

    agent_id = AgentId()
    (data_dir / str(agent_id)).mkdir()
    (data_dir / "agent-not-a-dir").write_text("not a directory")

    paths = ChangelingPaths(data_dir=data_dir)
    ids = _discover_changeling_ids(paths)

    assert len(ids) == 1
    assert str(ids[0]) == str(agent_id)


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


def test_build_table_matches_agents(tmp_path: Path) -> None:
    """Verify that _build_table matches changeling IDs to mng agents."""
    agent_id = AgentId()
    changeling_ids = [agent_id]
    mng_agents = [_make_agent_dict(str(agent_id), name="my-bot", state="RUNNING")]

    rows = _build_table(changeling_ids, mng_agents, _DEFAULT_DISPLAY_FIELDS)

    assert len(rows) == 1
    row = rows[0]
    # name, id, state, host.state
    assert row[0] == "my-bot"
    assert row[1] == str(agent_id)
    assert row[2] == "RUNNING"
    assert row[3] == "RUNNING"


def test_build_table_shows_empty_for_unknown_agent(tmp_path: Path) -> None:
    """Verify that _build_table shows empty fields for changeling IDs not in mng list."""
    agent_id = AgentId()
    changeling_ids = [agent_id]
    mng_agents: list[dict[str, Any]] = []

    rows = _build_table(changeling_ids, mng_agents, _DEFAULT_DISPLAY_FIELDS)

    assert len(rows) == 1
    row = rows[0]
    # name is empty, id is preserved, state is empty, host.state is empty
    assert row[0] == ""
    assert row[1] == str(agent_id)
    assert row[2] == ""
    assert row[3] == ""


def test_build_table_multiple_agents() -> None:
    """Verify that _build_table handles multiple changelings."""
    id1 = AgentId()
    id2 = AgentId()
    changeling_ids = [id1, id2]
    mng_agents = [
        _make_agent_dict(str(id1), name="bot-1", state="RUNNING"),
        _make_agent_dict(str(id2), name="bot-2", state="STOPPED"),
    ]

    rows = _build_table(changeling_ids, mng_agents, _DEFAULT_DISPLAY_FIELDS)

    assert len(rows) == 2
    assert rows[0][0] == "bot-1"
    assert rows[1][0] == "bot-2"


# --- CLI tests ---


def test_list_help() -> None:
    """Verify that changeling list --help works."""
    result = _RUNNER.invoke(cli, ["list", "--help"])

    assert result.exit_code == 0
    assert "List deployed changelings" in result.output


def test_list_empty_data_dir(tmp_path: Path) -> None:
    """Verify that changeling list shows 'No changelings found' for empty data dir."""
    data_dir = tmp_path / "changelings-data"
    data_dir.mkdir()

    result = _RUNNER.invoke(cli, ["list", "--data-dir", str(data_dir)])

    assert result.exit_code == 0
    assert "No changelings found" in result.output


def test_list_nonexistent_data_dir(tmp_path: Path) -> None:
    """Verify that changeling list handles nonexistent data dir gracefully."""
    result = _RUNNER.invoke(cli, ["list", "--data-dir", str(tmp_path / "nonexistent")])

    assert result.exit_code == 0
    assert "No changelings found" in result.output


def test_list_json_empty(tmp_path: Path) -> None:
    """Verify that changeling list --json outputs valid JSON for empty data dir."""
    data_dir = tmp_path / "changelings-data"
    data_dir.mkdir()

    result = _RUNNER.invoke(cli, ["-q", "list", "--json", "--data-dir", str(data_dir)])

    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data == {"changelings": []}
