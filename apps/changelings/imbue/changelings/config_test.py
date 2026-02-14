"""Tests for changelings config read/write."""

from pathlib import Path

import pytest

from imbue.changelings.config import add_changeling
from imbue.changelings.config import get_changeling
from imbue.changelings.config import load_config
from imbue.changelings.config import remove_changeling
from imbue.changelings.config import save_config
from imbue.changelings.config import upsert_changeling
from imbue.changelings.conftest import make_test_changeling
from imbue.changelings.data_types import ChangelingConfig
from imbue.changelings.data_types import ChangelingDefinition
from imbue.changelings.errors import ChangelingAlreadyExistsError
from imbue.changelings.errors import ChangelingConfigError
from imbue.changelings.errors import ChangelingNotFoundError
from imbue.changelings.primitives import ChangelingName
from imbue.changelings.primitives import CronSchedule


def test_load_config_returns_empty_when_no_file_exists() -> None:
    """Loading config when no file exists should return an empty config."""
    config = load_config()
    assert config.changeling_by_name == {}


def test_save_and_load_config_roundtrips_single_changeling() -> None:
    """Saving and loading a config with one changeling should roundtrip correctly."""
    definition = make_test_changeling(name="test-guardian")
    config = ChangelingConfig(
        changeling_by_name={definition.name: definition},
    )

    save_config(config)
    loaded = load_config()

    assert len(loaded.changeling_by_name) == 1
    loaded_def = loaded.changeling_by_name[ChangelingName("test-guardian")]
    assert loaded_def.name == ChangelingName("test-guardian")
    assert loaded_def.agent_type == "code-guardian"
    assert loaded_def.branch == "main"
    assert loaded_def.is_enabled is True


def test_save_and_load_config_roundtrips_multiple_changelings() -> None:
    """Saving and loading a config with multiple changelings should roundtrip correctly."""
    guardian = make_test_changeling(name="my-guardian")
    fairy = make_test_changeling(name="my-fairy", agent_type="claude")

    config = ChangelingConfig(
        changeling_by_name={guardian.name: guardian, fairy.name: fairy},
    )

    save_config(config)
    loaded = load_config()

    assert len(loaded.changeling_by_name) == 2
    assert ChangelingName("my-guardian") in loaded.changeling_by_name
    assert ChangelingName("my-fairy") in loaded.changeling_by_name


def test_save_and_load_config_preserves_optional_fields() -> None:
    """Optional fields like initial_message, secrets, and env_vars should survive roundtrip."""
    definition = ChangelingDefinition(
        name=ChangelingName("detailed-changeling"),
        schedule=CronSchedule("0 4 * * 1"),
        initial_message="Custom analysis instructions",
        agent_type="code-guardian",
        secrets=("CUSTOM_KEY", "OTHER_SECRET"),
        extra_mngr_args="--verbose",
        env_vars={"MY_VAR": "my_value"},
        mngr_options={"gpu": "a10g", "timeout": "600"},
        is_enabled=False,
    )
    config = ChangelingConfig(
        changeling_by_name={definition.name: definition},
    )

    save_config(config)
    loaded = load_config()

    loaded_def = loaded.changeling_by_name[ChangelingName("detailed-changeling")]
    assert loaded_def.schedule == CronSchedule("0 4 * * 1")
    assert loaded_def.initial_message == "Custom analysis instructions"
    assert loaded_def.secrets == ("CUSTOM_KEY", "OTHER_SECRET")
    assert loaded_def.extra_mngr_args == "--verbose"
    assert loaded_def.env_vars == {"MY_VAR": "my_value"}
    assert loaded_def.mngr_options == {"gpu": "a10g", "timeout": "600"}
    assert loaded_def.is_enabled is False


def test_add_changeling_adds_to_config() -> None:
    """add_changeling should persist a new changeling to the config file."""
    definition = make_test_changeling(name="test-guardian")

    result = add_changeling(definition)

    assert ChangelingName("test-guardian") in result.changeling_by_name
    # Verify it persisted by loading fresh
    loaded = load_config()
    assert ChangelingName("test-guardian") in loaded.changeling_by_name


def test_add_changeling_raises_on_duplicate_name() -> None:
    """add_changeling should raise ChangelingAlreadyExistsError for duplicates."""
    definition = make_test_changeling(name="test-guardian")
    add_changeling(definition)

    with pytest.raises(ChangelingAlreadyExistsError, match="test-guardian"):
        add_changeling(definition)


def test_remove_changeling_removes_from_config() -> None:
    """remove_changeling should remove the changeling from the config file."""
    definition = make_test_changeling(name="test-guardian")
    add_changeling(definition)

    result = remove_changeling(ChangelingName("test-guardian"))

    assert ChangelingName("test-guardian") not in result.changeling_by_name
    loaded = load_config()
    assert ChangelingName("test-guardian") not in loaded.changeling_by_name


def test_remove_changeling_raises_when_not_found() -> None:
    """remove_changeling should raise ChangelingNotFoundError if the name doesn't exist."""
    with pytest.raises(ChangelingNotFoundError, match="nonexistent"):
        remove_changeling(ChangelingName("nonexistent"))


def test_get_changeling_returns_definition() -> None:
    """get_changeling should return the matching ChangelingDefinition."""
    definition = make_test_changeling(name="test-guardian")
    add_changeling(definition)

    result = get_changeling(ChangelingName("test-guardian"))

    assert result.name == ChangelingName("test-guardian")
    assert result.agent_type == "code-guardian"


def test_get_changeling_raises_when_not_found() -> None:
    """get_changeling should raise ChangelingNotFoundError if the name doesn't exist."""
    with pytest.raises(ChangelingNotFoundError, match="nonexistent"):
        get_changeling(ChangelingName("nonexistent"))


def test_upsert_changeling_creates_when_not_exists() -> None:
    """upsert_changeling should create a new changeling if it doesn't exist."""
    definition = make_test_changeling(name="new-guardian")
    upsert_changeling(definition)

    result = get_changeling(ChangelingName("new-guardian"))
    assert result.name == ChangelingName("new-guardian")


def test_upsert_changeling_updates_when_exists() -> None:
    """upsert_changeling should overwrite an existing changeling."""
    original = make_test_changeling(name="test-guardian", branch="original")
    add_changeling(original)

    updated = make_test_changeling(name="test-guardian", branch="updated")
    upsert_changeling(updated)

    result = get_changeling(ChangelingName("test-guardian"))
    assert result.branch == "updated"


def test_load_config_raises_on_malformed_toml(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """load_config should raise ChangelingConfigError for malformed TOML."""
    config_dir = tmp_path / ".changelings"
    config_dir.mkdir()
    config_file = config_dir / "config.toml"
    config_file.write_text("this is not [ valid toml ]]]]")

    with pytest.raises(ChangelingConfigError, match="Failed to parse"):
        load_config()


def test_save_config_creates_directory_if_missing(tmp_path: Path) -> None:
    """save_config should create the ~/.changelings/ directory if it doesn't exist."""
    config = ChangelingConfig()
    save_config(config)

    config_dir = tmp_path / ".changelings"
    assert config_dir.exists()
    assert (config_dir / "config.toml").exists()
