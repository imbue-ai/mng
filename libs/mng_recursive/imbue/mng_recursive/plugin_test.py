"""Unit tests for mng_recursive plugin hooks."""

import json

import pytest

from imbue.mng_recursive.plugin import _get_chain_of_command
from imbue.mng_recursive.plugin import override_command_options


def test_override_skips_non_create_commands(monkeypatch: pytest.MonkeyPatch) -> None:
    """override_command_options should be a no-op for non-create commands."""
    monkeypatch.setenv("MNG_AGENT_ID", "abc123")
    params: dict[str, object] = {"label": (), "agent_env": ()}
    override_command_options(command_name="list", command_class=type, params=params)
    assert params["label"] == ()
    assert params["agent_env"] == ()


def test_override_skips_when_no_agent_id(monkeypatch: pytest.MonkeyPatch) -> None:
    """override_command_options should be a no-op when MNG_AGENT_ID is not set."""
    monkeypatch.delenv("MNG_AGENT_ID", raising=False)
    monkeypatch.delenv("MNG_CHAIN_OF_COMMAND", raising=False)
    params: dict[str, object] = {"label": (), "agent_env": ()}
    override_command_options(command_name="create", command_class=type, params=params)
    assert params["label"] == ()
    assert params["agent_env"] == ()


def test_override_sets_labels_and_env_for_first_level(monkeypatch: pytest.MonkeyPatch) -> None:
    """When MNG_AGENT_ID is set but no chain exists, should create a single-element chain."""
    monkeypatch.setenv("MNG_AGENT_ID", "agent-aaa")
    monkeypatch.delenv("MNG_CHAIN_OF_COMMAND", raising=False)
    params: dict[str, object] = {"label": (), "agent_env": ()}
    override_command_options(command_name="create", command_class=type, params=params)

    labels = params["label"]
    assert isinstance(labels, tuple)
    assert "commanding_agent_id=agent-aaa" in labels
    assert f"chain_of_command={json.dumps(['agent-aaa'])}" in labels

    env = params["agent_env"]
    assert isinstance(env, tuple)
    assert f"MNG_CHAIN_OF_COMMAND={json.dumps(['agent-aaa'])}" in env


def test_override_extends_existing_chain(monkeypatch: pytest.MonkeyPatch) -> None:
    """When both MNG_AGENT_ID and MNG_CHAIN_OF_COMMAND are set, should extend the chain."""
    monkeypatch.setenv("MNG_AGENT_ID", "agent-bbb")
    monkeypatch.setenv("MNG_CHAIN_OF_COMMAND", json.dumps(["agent-aaa"]))
    params: dict[str, object] = {"label": (), "agent_env": ()}
    override_command_options(command_name="create", command_class=type, params=params)

    labels = params["label"]
    assert isinstance(labels, tuple)
    assert "commanding_agent_id=agent-bbb" in labels
    expected_chain = json.dumps(["agent-aaa", "agent-bbb"])
    assert f"chain_of_command={expected_chain}" in labels

    env = params["agent_env"]
    assert isinstance(env, tuple)
    assert f"MNG_CHAIN_OF_COMMAND={expected_chain}" in env


def test_override_preserves_existing_labels(monkeypatch: pytest.MonkeyPatch) -> None:
    """Existing labels and env vars should be preserved when adding chain-of-command data."""
    monkeypatch.setenv("MNG_AGENT_ID", "agent-ccc")
    monkeypatch.delenv("MNG_CHAIN_OF_COMMAND", raising=False)
    params: dict[str, object] = {
        "label": ("project=myproject",),
        "agent_env": ("FOO=bar",),
    }
    override_command_options(command_name="create", command_class=type, params=params)

    labels = params["label"]
    assert isinstance(labels, tuple)
    assert "project=myproject" in labels
    assert "commanding_agent_id=agent-ccc" in labels

    env = params["agent_env"]
    assert isinstance(env, tuple)
    assert "FOO=bar" in env
    assert any("MNG_CHAIN_OF_COMMAND=" in e for e in env if isinstance(e, str))


def test_override_deeply_nested_chain(monkeypatch: pytest.MonkeyPatch) -> None:
    """Should correctly handle a deeply nested chain of command."""
    existing_chain = ["root-agent", "level-1", "level-2"]
    monkeypatch.setenv("MNG_AGENT_ID", "level-3")
    monkeypatch.setenv("MNG_CHAIN_OF_COMMAND", json.dumps(existing_chain))
    params: dict[str, object] = {"label": (), "agent_env": ()}
    override_command_options(command_name="create", command_class=type, params=params)

    expected_chain = [*existing_chain, "level-3"]
    labels = params["label"]
    assert isinstance(labels, tuple)
    assert f"chain_of_command={json.dumps(expected_chain)}" in labels

    env = params["agent_env"]
    assert isinstance(env, tuple)
    assert f"MNG_CHAIN_OF_COMMAND={json.dumps(expected_chain)}" in env


def test_get_chain_of_command_returns_empty_when_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    """_get_chain_of_command should return empty list when env var is not set."""
    monkeypatch.delenv("MNG_CHAIN_OF_COMMAND", raising=False)
    assert _get_chain_of_command() == []


def test_get_chain_of_command_returns_empty_for_empty_string(monkeypatch: pytest.MonkeyPatch) -> None:
    """_get_chain_of_command should return empty list when env var is empty string."""
    monkeypatch.setenv("MNG_CHAIN_OF_COMMAND", "")
    assert _get_chain_of_command() == []


def test_get_chain_of_command_parses_json(monkeypatch: pytest.MonkeyPatch) -> None:
    """_get_chain_of_command should parse JSON list from env var."""
    monkeypatch.setenv("MNG_CHAIN_OF_COMMAND", json.dumps(["a", "b", "c"]))
    assert _get_chain_of_command() == ["a", "b", "c"]
