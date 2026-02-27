from pathlib import Path

import pytest

from imbue.changelings.core.zygote import ZYGOTE_CONFIG_FILENAME
from imbue.changelings.core.zygote import ZygoteCommand
from imbue.changelings.core.zygote import ZygoteConfig
from imbue.changelings.core.zygote import ZygoteConfigError
from imbue.changelings.core.zygote import ZygoteName
from imbue.changelings.core.zygote import ZygoteNotFoundError
from imbue.changelings.core.zygote import load_zygote_config
from imbue.imbue_common.primitives import PositiveInt
from imbue.mng.primitives import AgentTypeName


def test_load_valid_zygote_config(tmp_path: Path) -> None:
    config_file = tmp_path / ZYGOTE_CONFIG_FILENAME
    config_file.write_text('[changeling]\nname = "test-agent"\ncommand = "python server.py"\nport = 8080\n')

    config = load_zygote_config(tmp_path)

    assert config.name == "test-agent"
    assert config.command == "python server.py"
    assert config.port == 8080
    assert config.description == ""
    assert config.agent_type is None


def test_load_zygote_config_with_description(tmp_path: Path) -> None:
    config_file = tmp_path / ZYGOTE_CONFIG_FILENAME
    config_file.write_text(
        '[changeling]\nname = "my-bot"\ncommand = "python bot.py"\nport = 9000\ndescription = "A helpful bot"\n'
    )

    config = load_zygote_config(tmp_path)

    assert config.name == "my-bot"
    assert config.description == "A helpful bot"


def test_load_zygote_config_with_agent_type(tmp_path: Path) -> None:
    config_file = tmp_path / ZYGOTE_CONFIG_FILENAME
    config_file.write_text('[changeling]\nname = "elena"\nagent_type = "elena-code"\n')

    config = load_zygote_config(tmp_path)

    assert config.name == "elena"
    assert config.agent_type == AgentTypeName("elena-code")
    assert config.command is None
    assert config.port is None


def test_load_zygote_config_with_agent_type_and_description(tmp_path: Path) -> None:
    config_file = tmp_path / ZYGOTE_CONFIG_FILENAME
    config_file.write_text(
        '[changeling]\nname = "elena"\nagent_type = "elena-code"\ndescription = "A conversational AI"\n'
    )

    config = load_zygote_config(tmp_path)

    assert config.agent_type == AgentTypeName("elena-code")
    assert config.description == "A conversational AI"


def test_load_zygote_config_raises_when_file_missing(tmp_path: Path) -> None:
    with pytest.raises(ZygoteNotFoundError, match="No changeling.toml found"):
        load_zygote_config(tmp_path)


def test_load_zygote_config_raises_for_invalid_toml(tmp_path: Path) -> None:
    config_file = tmp_path / ZYGOTE_CONFIG_FILENAME
    config_file.write_text("this is not valid toml [[[")

    with pytest.raises(ZygoteConfigError, match="Invalid TOML"):
        load_zygote_config(tmp_path)


def test_load_zygote_config_raises_when_changeling_section_missing(tmp_path: Path) -> None:
    config_file = tmp_path / ZYGOTE_CONFIG_FILENAME
    config_file.write_text('[other]\nkey = "value"\n')

    with pytest.raises(ZygoteConfigError, match="Missing \\[changeling\\] section"):
        load_zygote_config(tmp_path)


def test_load_zygote_config_raises_for_missing_required_fields(tmp_path: Path) -> None:
    """Without agent_type, both command and port are required."""
    config_file = tmp_path / ZYGOTE_CONFIG_FILENAME
    config_file.write_text('[changeling]\nname = "test"\n')

    with pytest.raises(ZygoteConfigError, match="Invalid changeling config"):
        load_zygote_config(tmp_path)


def test_load_zygote_config_raises_when_command_missing_without_agent_type(tmp_path: Path) -> None:
    config_file = tmp_path / ZYGOTE_CONFIG_FILENAME
    config_file.write_text('[changeling]\nname = "test"\nport = 8080\n')

    with pytest.raises(ZygoteConfigError, match="Invalid changeling config"):
        load_zygote_config(tmp_path)


def test_load_zygote_config_raises_when_port_missing_without_agent_type(tmp_path: Path) -> None:
    config_file = tmp_path / ZYGOTE_CONFIG_FILENAME
    config_file.write_text('[changeling]\nname = "test"\ncommand = "python s.py"\n')

    with pytest.raises(ZygoteConfigError, match="Invalid changeling config"):
        load_zygote_config(tmp_path)


def test_load_zygote_config_raises_for_invalid_port(tmp_path: Path) -> None:
    config_file = tmp_path / ZYGOTE_CONFIG_FILENAME
    config_file.write_text('[changeling]\nname = "test"\ncommand = "python s.py"\nport = 0\n')

    with pytest.raises(ZygoteConfigError, match="Invalid changeling config"):
        load_zygote_config(tmp_path)


def test_zygote_config_is_frozen() -> None:
    config = ZygoteConfig(
        name=ZygoteName("test"),
        command=ZygoteCommand("python s.py"),
        port=PositiveInt(8080),
    )

    assert config.model_config.get("frozen") is True


def test_zygote_config_with_agent_type_is_frozen() -> None:
    config = ZygoteConfig(
        name=ZygoteName("test"),
        agent_type=AgentTypeName("elena-code"),
    )

    assert config.model_config.get("frozen") is True


def test_zygote_config_rejects_agent_type_with_command(tmp_path: Path) -> None:
    """agent_type and command are mutually exclusive."""
    config_file = tmp_path / ZYGOTE_CONFIG_FILENAME
    config_file.write_text('[changeling]\nname = "test"\nagent_type = "elena-code"\ncommand = "python s.py"\n')

    with pytest.raises(ZygoteConfigError, match="Invalid changeling config"):
        load_zygote_config(tmp_path)


def test_zygote_config_rejects_agent_type_with_port(tmp_path: Path) -> None:
    """agent_type and port are mutually exclusive."""
    config_file = tmp_path / ZYGOTE_CONFIG_FILENAME
    config_file.write_text('[changeling]\nname = "test"\nagent_type = "elena-code"\nport = 8080\n')

    with pytest.raises(ZygoteConfigError, match="Invalid changeling config"):
        load_zygote_config(tmp_path)
