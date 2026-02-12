import json
from pathlib import Path

import click
import pytest
from click.shell_completion import CompletionItem

from imbue.mngr.cli.completion import _read_agent_names_from_disk
from imbue.mngr.cli.completion import complete_agent_name


def _create_agent_data_file(agents_dir: Path, agent_id: str, name: str) -> None:
    """Create a minimal agent data.json file for testing."""
    agent_dir = agents_dir / agent_id
    agent_dir.mkdir(parents=True, exist_ok=True)
    data = {"id": agent_id, "name": name, "type": "generic"}
    (agent_dir / "data.json").write_text(json.dumps(data))


def test_read_agent_names_from_disk_returns_names(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    host_dir = tmp_path / ".mngr"
    agents_dir = host_dir / "agents"
    monkeypatch.setenv("MNGR_HOST_DIR", str(host_dir))

    _create_agent_data_file(agents_dir, "agent-aaa", "alpha-agent")
    _create_agent_data_file(agents_dir, "agent-bbb", "beta-agent")

    result = _read_agent_names_from_disk()

    assert result == ["alpha-agent", "beta-agent"]


def test_read_agent_names_from_disk_returns_sorted(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    host_dir = tmp_path / ".mngr"
    agents_dir = host_dir / "agents"
    monkeypatch.setenv("MNGR_HOST_DIR", str(host_dir))

    _create_agent_data_file(agents_dir, "agent-ccc", "zebra")
    _create_agent_data_file(agents_dir, "agent-aaa", "alpha")
    _create_agent_data_file(agents_dir, "agent-bbb", "middle")

    result = _read_agent_names_from_disk()

    assert result == ["alpha", "middle", "zebra"]


def test_read_agent_names_from_disk_returns_empty_when_dir_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MNGR_HOST_DIR", str(tmp_path / "nonexistent"))

    result = _read_agent_names_from_disk()

    assert result == []


def test_read_agent_names_from_disk_skips_malformed_json(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    host_dir = tmp_path / ".mngr"
    agents_dir = host_dir / "agents"
    monkeypatch.setenv("MNGR_HOST_DIR", str(host_dir))

    _create_agent_data_file(agents_dir, "agent-aaa", "good-agent")

    # Create malformed data.json
    bad_dir = agents_dir / "agent-bad"
    bad_dir.mkdir(parents=True, exist_ok=True)
    (bad_dir / "data.json").write_text("not valid json {{{")

    result = _read_agent_names_from_disk()

    assert result == ["good-agent"]


def test_read_agent_names_from_disk_skips_missing_name_field(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    host_dir = tmp_path / ".mngr"
    agents_dir = host_dir / "agents"
    monkeypatch.setenv("MNGR_HOST_DIR", str(host_dir))

    _create_agent_data_file(agents_dir, "agent-aaa", "good-agent")

    # Create data.json without "name" field
    no_name_dir = agents_dir / "agent-noname"
    no_name_dir.mkdir(parents=True, exist_ok=True)
    (no_name_dir / "data.json").write_text(json.dumps({"id": "agent-noname", "type": "generic"}))

    result = _read_agent_names_from_disk()

    assert result == ["good-agent"]


def test_read_agent_names_from_disk_skips_empty_name(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    host_dir = tmp_path / ".mngr"
    agents_dir = host_dir / "agents"
    monkeypatch.setenv("MNGR_HOST_DIR", str(host_dir))

    _create_agent_data_file(agents_dir, "agent-aaa", "good-agent")

    # Create data.json with empty name
    empty_dir = agents_dir / "agent-empty"
    empty_dir.mkdir(parents=True, exist_ok=True)
    (empty_dir / "data.json").write_text(json.dumps({"id": "agent-empty", "name": "", "type": "generic"}))

    result = _read_agent_names_from_disk()

    assert result == ["good-agent"]


def test_read_agent_names_from_disk_skips_non_dir_entries(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    host_dir = tmp_path / ".mngr"
    agents_dir = host_dir / "agents"
    agents_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("MNGR_HOST_DIR", str(host_dir))

    _create_agent_data_file(agents_dir, "agent-aaa", "good-agent")

    # Create a non-directory file in the agents directory
    (agents_dir / "some-file.txt").write_text("not a directory")

    result = _read_agent_names_from_disk()

    assert result == ["good-agent"]


def test_read_agent_names_from_disk_uses_default_host_dir(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Clear MNGR_HOST_DIR so it uses the default ~/.mngr
    monkeypatch.delenv("MNGR_HOST_DIR", raising=False)
    # Point HOME to tmp_path so ~/.mngr is under tmp_path
    monkeypatch.setenv("HOME", str(tmp_path))

    agents_dir = tmp_path / ".mngr" / "agents"
    _create_agent_data_file(agents_dir, "agent-aaa", "home-agent")

    result = _read_agent_names_from_disk()

    assert result == ["home-agent"]


def test_complete_agent_name_filters_by_prefix(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    host_dir = tmp_path / ".mngr"
    agents_dir = host_dir / "agents"
    monkeypatch.setenv("MNGR_HOST_DIR", str(host_dir))

    _create_agent_data_file(agents_dir, "agent-aaa", "alpha-agent")
    _create_agent_data_file(agents_dir, "agent-bbb", "beta-agent")
    _create_agent_data_file(agents_dir, "agent-ccc", "alpha-other")

    ctx = click.Context(click.Command("test"))
    param = click.Argument(["agent"])

    result = complete_agent_name(ctx, param, "alpha")

    assert len(result) == 2
    assert all(isinstance(item, CompletionItem) for item in result)
    names = [item.value for item in result]
    assert names == ["alpha-agent", "alpha-other"]


def test_complete_agent_name_returns_all_when_incomplete_is_empty(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    host_dir = tmp_path / ".mngr"
    agents_dir = host_dir / "agents"
    monkeypatch.setenv("MNGR_HOST_DIR", str(host_dir))

    _create_agent_data_file(agents_dir, "agent-aaa", "alpha")
    _create_agent_data_file(agents_dir, "agent-bbb", "beta")

    ctx = click.Context(click.Command("test"))
    param = click.Argument(["agent"])

    result = complete_agent_name(ctx, param, "")

    assert len(result) == 2
    names = [item.value for item in result]
    assert names == ["alpha", "beta"]


def test_complete_agent_name_returns_empty_when_no_match(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    host_dir = tmp_path / ".mngr"
    agents_dir = host_dir / "agents"
    monkeypatch.setenv("MNGR_HOST_DIR", str(host_dir))

    _create_agent_data_file(agents_dir, "agent-aaa", "alpha")

    ctx = click.Context(click.Command("test"))
    param = click.Argument(["agent"])

    result = complete_agent_name(ctx, param, "zzz")

    assert result == []
