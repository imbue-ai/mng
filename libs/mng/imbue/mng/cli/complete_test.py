import json
from pathlib import Path

import pytest

from imbue.mng.cli.complete import _filter_aliases
from imbue.mng.cli.complete import _format_output
from imbue.mng.cli.complete import _get_completions
from imbue.mng.cli.complete import _read_agent_names
from imbue.mng.cli.complete import _read_cache


def _write_command_cache(cache_dir: Path, data: dict[str, object]) -> None:
    """Write a command completions cache file for testing."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    (cache_dir / ".command_completions.json").write_text(json.dumps(data))


def _write_agent_cache(cache_dir: Path, names: list[str]) -> None:
    """Write an agent completions cache file for testing."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    data = {"names": names, "updated_at": "2025-01-01T00:00:00+00:00"}
    (cache_dir / ".agent_completions.json").write_text(json.dumps(data))


def _make_cache_data(
    commands: list[str] | None = None,
    aliases: dict[str, str] | None = None,
    subcommand_by_command: dict[str, list[str]] | None = None,
    options_by_command: dict[str, list[str]] | None = None,
    option_choices: dict[str, list[str]] | None = None,
    agent_name_arguments: list[str] | None = None,
) -> dict:
    """Build a command completions cache dict with sensible defaults."""
    return {
        "commands": commands or [],
        "aliases": aliases or {},
        "subcommand_by_command": subcommand_by_command or {},
        "options_by_command": options_by_command or {},
        "option_choices": option_choices or {},
        "agent_name_arguments": agent_name_arguments or [],
    }


# =============================================================================
# _read_cache tests
# =============================================================================


def test_read_cache_returns_data(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MNG_COMPLETION_CACHE_DIR", str(tmp_path))
    data = _make_cache_data(commands=["create", "list"])
    _write_command_cache(tmp_path, data)

    result = _read_cache()

    assert result["commands"] == ["create", "list"]


def test_read_cache_returns_empty_dict_when_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MNG_COMPLETION_CACHE_DIR", str(tmp_path))

    result = _read_cache()

    assert result == {}


def test_read_cache_returns_empty_dict_for_malformed_json(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MNG_COMPLETION_CACHE_DIR", str(tmp_path))
    (tmp_path / ".command_completions.json").write_text("not json {{{")

    result = _read_cache()

    assert result == {}


# =============================================================================
# _read_agent_names tests
# =============================================================================


def test_read_agent_names_returns_names(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MNG_COMPLETION_CACHE_DIR", str(tmp_path))
    _write_agent_cache(tmp_path, ["beta", "alpha"])

    result = _read_agent_names()

    assert result == ["alpha", "beta"]


def test_read_agent_names_returns_empty_when_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MNG_COMPLETION_CACHE_DIR", str(tmp_path))

    result = _read_agent_names()

    assert result == []


# =============================================================================
# _filter_aliases tests
# =============================================================================


def test_filter_aliases_drops_alias_when_canonical_matches() -> None:
    commands = ["c", "config", "connect", "create"]
    aliases = {"c": "create", "cfg": "config"}

    result = _filter_aliases(commands, aliases, "c")

    assert "c" not in result
    assert "config" in result
    assert "connect" in result
    assert "create" in result


def test_filter_aliases_keeps_alias_when_canonical_does_not_match() -> None:
    commands = ["c", "config", "connect", "create"]
    aliases = {"c": "create"}

    result = _filter_aliases(commands, aliases, "cfg")

    # "cfg" does not match anything, so nothing is returned
    assert result == []


def test_filter_aliases_no_aliases() -> None:
    commands = ["create", "list", "destroy"]
    aliases: dict[str, str] = {}

    result = _filter_aliases(commands, aliases, "")

    assert result == ["create", "list", "destroy"]


# =============================================================================
# _get_completions tests
# =============================================================================


def test_get_completions_command_name(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Completing the command name at position 1."""
    monkeypatch.setenv("MNG_COMPLETION_CACHE_DIR", str(tmp_path))
    data = _make_cache_data(
        commands=["ask", "config", "connect", "create", "destroy", "list"],
    )
    _write_command_cache(tmp_path, data)

    monkeypatch.setenv("COMP_WORDS", "mng cr")
    monkeypatch.setenv("COMP_CWORD", "1")

    result = _get_completions("zsh")

    assert result == ["create"]


def test_get_completions_command_name_all(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Completing with empty incomplete returns all commands."""
    monkeypatch.setenv("MNG_COMPLETION_CACHE_DIR", str(tmp_path))
    data = _make_cache_data(commands=["ask", "create", "list"])
    _write_command_cache(tmp_path, data)

    monkeypatch.setenv("COMP_WORDS", "mng ")
    monkeypatch.setenv("COMP_CWORD", "1")

    result = _get_completions("zsh")

    assert result == ["ask", "create", "list"]


def test_get_completions_alias_filtering(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Aliases should be filtered when their canonical name also matches."""
    monkeypatch.setenv("MNG_COMPLETION_CACHE_DIR", str(tmp_path))
    data = _make_cache_data(
        commands=["c", "cfg", "config", "connect", "create"],
        aliases={"c": "create", "cfg": "config"},
    )
    _write_command_cache(tmp_path, data)

    monkeypatch.setenv("COMP_WORDS", "mng c")
    monkeypatch.setenv("COMP_CWORD", "1")

    result = _get_completions("zsh")

    assert "create" in result
    assert "config" in result
    assert "connect" in result
    assert "c" not in result
    assert "cfg" not in result


def test_get_completions_subcommand(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Completing subcommands of a group command."""
    monkeypatch.setenv("MNG_COMPLETION_CACHE_DIR", str(tmp_path))
    data = _make_cache_data(
        commands=["config"],
        subcommand_by_command={"config": ["edit", "get", "list", "set"]},
    )
    _write_command_cache(tmp_path, data)

    monkeypatch.setenv("COMP_WORDS", "mng config ")
    monkeypatch.setenv("COMP_CWORD", "2")

    result = _get_completions("zsh")

    assert result == ["edit", "get", "list", "set"]


def test_get_completions_subcommand_with_prefix(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Completing subcommands with a prefix."""
    monkeypatch.setenv("MNG_COMPLETION_CACHE_DIR", str(tmp_path))
    data = _make_cache_data(
        commands=["config"],
        subcommand_by_command={"config": ["edit", "get", "list", "set"]},
    )
    _write_command_cache(tmp_path, data)

    monkeypatch.setenv("COMP_WORDS", "mng config s")
    monkeypatch.setenv("COMP_CWORD", "2")

    result = _get_completions("zsh")

    assert result == ["set"]


def test_get_completions_options(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Completing options for a command."""
    monkeypatch.setenv("MNG_COMPLETION_CACHE_DIR", str(tmp_path))
    data = _make_cache_data(
        commands=["list"],
        options_by_command={"list": ["--format", "--help", "--running", "--stopped"]},
    )
    _write_command_cache(tmp_path, data)

    monkeypatch.setenv("COMP_WORDS", "mng list --f")
    monkeypatch.setenv("COMP_CWORD", "2")

    result = _get_completions("zsh")

    assert result == ["--format"]


def test_get_completions_option_choices(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Completing values for an option with choices."""
    monkeypatch.setenv("MNG_COMPLETION_CACHE_DIR", str(tmp_path))
    data = _make_cache_data(
        commands=["list"],
        options_by_command={"list": ["--format", "--help"]},
        option_choices={"list.--format": ["json", "table", "jsonl"]},
    )
    _write_command_cache(tmp_path, data)

    monkeypatch.setenv("COMP_WORDS", "mng list --format ")
    monkeypatch.setenv("COMP_CWORD", "3")

    result = _get_completions("zsh")

    assert result == ["json", "table", "jsonl"]


def test_get_completions_option_choices_with_prefix(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Completing values for an option with choices and a prefix."""
    monkeypatch.setenv("MNG_COMPLETION_CACHE_DIR", str(tmp_path))
    data = _make_cache_data(
        commands=["list"],
        options_by_command={"list": ["--format", "--help"]},
        option_choices={"list.--format": ["json", "table", "jsonl"]},
    )
    _write_command_cache(tmp_path, data)

    monkeypatch.setenv("COMP_WORDS", "mng list --format j")
    monkeypatch.setenv("COMP_CWORD", "3")

    result = _get_completions("zsh")

    assert result == ["json", "jsonl"]


def test_get_completions_subcommand_options(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Completing options for a subcommand (dot-separated key)."""
    monkeypatch.setenv("MNG_COMPLETION_CACHE_DIR", str(tmp_path))
    data = _make_cache_data(
        commands=["config"],
        subcommand_by_command={"config": ["get", "set"]},
        options_by_command={"config.get": ["--help", "--scope"]},
    )
    _write_command_cache(tmp_path, data)

    monkeypatch.setenv("COMP_WORDS", "mng config get --")
    monkeypatch.setenv("COMP_CWORD", "3")

    result = _get_completions("zsh")

    assert "--help" in result
    assert "--scope" in result


def test_get_completions_subcommand_option_choices(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Completing values for a subcommand option with choices."""
    monkeypatch.setenv("MNG_COMPLETION_CACHE_DIR", str(tmp_path))
    data = _make_cache_data(
        commands=["config"],
        subcommand_by_command={"config": ["get", "set"]},
        options_by_command={"config.get": ["--help", "--scope"]},
        option_choices={"config.get.--scope": ["user", "project", "local"]},
    )
    _write_command_cache(tmp_path, data)

    monkeypatch.setenv("COMP_WORDS", "mng config get --scope ")
    monkeypatch.setenv("COMP_CWORD", "4")

    result = _get_completions("zsh")

    assert result == ["user", "project", "local"]


def test_get_completions_agent_names(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Completing agent names for commands that accept agent arguments."""
    monkeypatch.setenv("MNG_COMPLETION_CACHE_DIR", str(tmp_path))
    data = _make_cache_data(
        commands=["connect", "list"],
        agent_name_arguments=["connect"],
    )
    _write_command_cache(tmp_path, data)
    _write_agent_cache(tmp_path, ["my-agent", "other-agent"])

    monkeypatch.setenv("COMP_WORDS", "mng connect ")
    monkeypatch.setenv("COMP_CWORD", "2")

    result = _get_completions("zsh")

    assert result == ["my-agent", "other-agent"]


def test_get_completions_agent_names_with_prefix(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Completing agent names with a prefix filter."""
    monkeypatch.setenv("MNG_COMPLETION_CACHE_DIR", str(tmp_path))
    data = _make_cache_data(
        commands=["connect"],
        agent_name_arguments=["connect"],
    )
    _write_command_cache(tmp_path, data)
    _write_agent_cache(tmp_path, ["my-agent", "other-agent"])

    monkeypatch.setenv("COMP_WORDS", "mng connect my")
    monkeypatch.setenv("COMP_CWORD", "2")

    result = _get_completions("zsh")

    assert result == ["my-agent"]


def test_get_completions_no_agent_names_for_non_agent_command(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Commands not in agent_name_arguments should not complete agent names."""
    monkeypatch.setenv("MNG_COMPLETION_CACHE_DIR", str(tmp_path))
    data = _make_cache_data(
        commands=["list"],
        agent_name_arguments=["connect"],
    )
    _write_command_cache(tmp_path, data)
    _write_agent_cache(tmp_path, ["my-agent"])

    monkeypatch.setenv("COMP_WORDS", "mng list ")
    monkeypatch.setenv("COMP_CWORD", "2")

    result = _get_completions("zsh")

    assert result == []


def test_get_completions_alias_resolves_to_canonical(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An alias typed as the command should resolve to the canonical name for option lookup."""
    monkeypatch.setenv("MNG_COMPLETION_CACHE_DIR", str(tmp_path))
    data = _make_cache_data(
        commands=["conn", "connect"],
        aliases={"conn": "connect"},
        options_by_command={"connect": ["--help", "--start"]},
    )
    _write_command_cache(tmp_path, data)

    monkeypatch.setenv("COMP_WORDS", "mng conn --")
    monkeypatch.setenv("COMP_CWORD", "2")

    result = _get_completions("zsh")

    assert "--help" in result
    assert "--start" in result


def test_get_completions_empty_cache(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When the cache is missing, no completions are returned."""
    monkeypatch.setenv("MNG_COMPLETION_CACHE_DIR", str(tmp_path))

    monkeypatch.setenv("COMP_WORDS", "mng ")
    monkeypatch.setenv("COMP_CWORD", "1")

    result = _get_completions("zsh")

    assert result == []


def test_get_completions_invalid_comp_cword(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When COMP_CWORD is not a valid integer, no completions are returned."""
    monkeypatch.setenv("MNG_COMPLETION_CACHE_DIR", str(tmp_path))
    monkeypatch.setenv("COMP_WORDS", "mng ")
    monkeypatch.setenv("COMP_CWORD", "not-a-number")

    result = _get_completions("zsh")

    assert result == []


# =============================================================================
# _format_output tests
# =============================================================================


def test_format_output_zsh() -> None:
    result = _format_output(["create", "list"], "zsh")

    assert result == "plain\ncreate\n_\nplain\nlist\n_"


def test_format_output_bash() -> None:
    result = _format_output(["create", "list"], "bash")

    assert result == "plain,create\nplain,list"


def test_format_output_empty() -> None:
    assert _format_output([], "zsh") == ""
    assert _format_output([], "bash") == ""
