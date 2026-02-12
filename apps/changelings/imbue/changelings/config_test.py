from pathlib import Path

import pytest

from imbue.changelings.config import _config_to_toml
from imbue.changelings.config import _parse_config
from imbue.changelings.config import add_changeling
from imbue.changelings.config import load_config
from imbue.changelings.config import remove_changeling
from imbue.changelings.config import save_config
from imbue.changelings.conftest import make_test_definition as _make_definition
from imbue.changelings.data_types import ChangelingConfig
from imbue.changelings.errors import ChangelingAlreadyExistsError
from imbue.changelings.errors import ChangelingConfigError
from imbue.changelings.errors import ChangelingNotFoundError
from imbue.changelings.primitives import ChangelingName
from imbue.changelings.primitives import ChangelingTemplateName
from imbue.changelings.primitives import CronSchedule
from imbue.changelings.primitives import GitRepoUrl


class TestAddChangeling:
    def test_add_to_empty_config(self) -> None:
        config = ChangelingConfig()
        definition = _make_definition()
        result = add_changeling(config, definition)

        assert ChangelingName("test-fairy") in result.changeling_by_name
        assert result.changeling_by_name[ChangelingName("test-fairy")] == definition

    def test_add_second_changeling(self) -> None:
        config = ChangelingConfig()
        config = add_changeling(config, _make_definition("first"))
        config = add_changeling(config, _make_definition("second"))

        assert len(config.changeling_by_name) == 2
        assert ChangelingName("first") in config.changeling_by_name
        assert ChangelingName("second") in config.changeling_by_name

    def test_add_duplicate_raises(self) -> None:
        config = ChangelingConfig()
        config = add_changeling(config, _make_definition("dupe"))

        with pytest.raises(ChangelingAlreadyExistsError) as exc_info:
            add_changeling(config, _make_definition("dupe"))
        assert exc_info.value.name == "dupe"

    def test_add_does_not_mutate_original(self) -> None:
        config = ChangelingConfig()
        new_config = add_changeling(config, _make_definition())

        assert len(config.changeling_by_name) == 0
        assert len(new_config.changeling_by_name) == 1


class TestRemoveChangeling:
    def test_remove_existing(self) -> None:
        config = add_changeling(ChangelingConfig(), _make_definition("to-remove"))
        result = remove_changeling(config, ChangelingName("to-remove"))

        assert len(result.changeling_by_name) == 0

    def test_remove_nonexistent_raises(self) -> None:
        config = ChangelingConfig()

        with pytest.raises(ChangelingNotFoundError) as exc_info:
            remove_changeling(config, ChangelingName("nope"))
        assert exc_info.value.name == "nope"

    def test_remove_does_not_mutate_original(self) -> None:
        config = add_changeling(ChangelingConfig(), _make_definition("keep-me"))
        remove_changeling(config, ChangelingName("keep-me"))

        assert len(config.changeling_by_name) == 1


class TestParseConfig:
    def test_empty_raw(self) -> None:
        result = _parse_config({})
        assert len(result.changeling_by_name) == 0

    def test_single_changeling(self) -> None:
        raw = {
            "changelings": {
                "my-fairy": {
                    "template": "fixme-fairy",
                    "schedule": "0 3 * * *",
                    "repo": "git@github.com:org/repo.git",
                }
            }
        }
        result = _parse_config(raw)
        assert ChangelingName("my-fairy") in result.changeling_by_name
        defn = result.changeling_by_name[ChangelingName("my-fairy")]
        assert defn.template == ChangelingTemplateName("fixme-fairy")
        assert defn.schedule == CronSchedule("0 3 * * *")
        assert defn.branch == "main"
        assert defn.is_enabled is True

    def test_changeling_with_all_fields(self) -> None:
        raw = {
            "changelings": {
                "custom": {
                    "template": "code-guardian",
                    "schedule": "0 4 * * 1",
                    "repo": "https://github.com/org/repo.git",
                    "branch": "develop",
                    "message": "custom message",
                    "agent_type": "opencode",
                    "extra_mngr_args": "--timeout 300",
                    "env_vars": {"FOO": "bar"},
                    "is_enabled": False,
                }
            }
        }
        result = _parse_config(raw)
        defn = result.changeling_by_name[ChangelingName("custom")]
        assert defn.branch == "develop"
        assert defn.message == "custom message"
        assert defn.agent_type == "opencode"
        assert defn.extra_mngr_args == "--timeout 300"
        assert defn.env_vars == {"FOO": "bar"}
        assert defn.is_enabled is False

    def test_invalid_changeling_table_raises(self) -> None:
        raw = {"changelings": {"bad": "not-a-table"}}
        with pytest.raises(ChangelingConfigError, match="must be a table"):
            _parse_config(raw)

    def test_changelings_not_a_table_raises(self) -> None:
        raw = {"changelings": "bad"}
        with pytest.raises(ChangelingConfigError, match="must be a table"):
            _parse_config(raw)

    def test_missing_required_field_raises(self) -> None:
        raw = {"changelings": {"bad": {"template": "fixme-fairy"}}}
        with pytest.raises(ChangelingConfigError, match="Invalid changeling"):
            _parse_config(raw)


class TestConfigToToml:
    def test_empty_config(self) -> None:
        config = ChangelingConfig()
        doc = _config_to_toml(config)
        assert len(doc) == 0

    def test_single_changeling_defaults(self) -> None:
        config = add_changeling(ChangelingConfig(), _make_definition())
        doc = _config_to_toml(config)

        assert "changelings" in doc
        changeling_table = doc["changelings"]["test-fairy"]  # type: ignore[index]
        assert changeling_table["template"] == "fixme-fairy"  # type: ignore[index]
        assert changeling_table["schedule"] == "0 3 * * *"  # type: ignore[index]
        assert changeling_table["repo"] == "git@github.com:org/repo.git"  # type: ignore[index]
        # Defaults should not be written
        assert "branch" not in changeling_table  # type: ignore[operator]
        assert "agent_type" not in changeling_table  # type: ignore[operator]
        assert "is_enabled" not in changeling_table  # type: ignore[operator]

    def test_non_default_values_written(self) -> None:
        defn = _make_definition(branch="develop", agent_type="opencode", is_enabled=False)
        config = add_changeling(ChangelingConfig(), defn)
        doc = _config_to_toml(config)

        changeling_table = doc["changelings"]["test-fairy"]  # type: ignore[index]
        assert changeling_table["branch"] == "develop"  # type: ignore[index]
        assert changeling_table["agent_type"] == "opencode"  # type: ignore[index]
        assert changeling_table["is_enabled"] is False  # type: ignore[index]


class TestLoadSaveRoundtrip:
    def test_load_nonexistent_returns_empty(self, tmp_path: Path) -> None:
        config = load_config(tmp_path / "nonexistent.toml")
        assert len(config.changeling_by_name) == 0

    def test_save_and_load_roundtrip(self, tmp_path: Path) -> None:
        config_path = tmp_path / "config.toml"
        original = add_changeling(ChangelingConfig(), _make_definition())
        original = add_changeling(original, _make_definition("second", template="code-guardian"))

        save_config(original, config_path)
        loaded = load_config(config_path)

        assert len(loaded.changeling_by_name) == 2
        assert ChangelingName("test-fairy") in loaded.changeling_by_name
        assert ChangelingName("second") in loaded.changeling_by_name

        fairy = loaded.changeling_by_name[ChangelingName("test-fairy")]
        assert fairy.template == ChangelingTemplateName("fixme-fairy")
        assert fairy.schedule == CronSchedule("0 3 * * *")
        assert fairy.repo == GitRepoUrl("git@github.com:org/repo.git")

    def test_save_creates_parent_directories(self, tmp_path: Path) -> None:
        config_path = tmp_path / "deep" / "nested" / "config.toml"
        config = add_changeling(ChangelingConfig(), _make_definition())
        save_config(config, config_path)

        assert config_path.exists()
        loaded = load_config(config_path)
        assert len(loaded.changeling_by_name) == 1

    def test_roundtrip_preserves_non_default_fields(self, tmp_path: Path) -> None:
        config_path = tmp_path / "config.toml"
        defn = _make_definition(
            branch="develop",
            message="custom message",
            agent_type="opencode",
            extra_mngr_args="--timeout 300",
            env_vars={"KEY": "value"},
            is_enabled=False,
        )
        original = add_changeling(ChangelingConfig(), defn)
        save_config(original, config_path)
        loaded = load_config(config_path)

        loaded_defn = loaded.changeling_by_name[ChangelingName("test-fairy")]
        assert loaded_defn.branch == "develop"
        assert loaded_defn.message == "custom message"
        assert loaded_defn.agent_type == "opencode"
        assert loaded_defn.extra_mngr_args == "--timeout 300"
        assert loaded_defn.env_vars == {"KEY": "value"}
        assert loaded_defn.is_enabled is False

    def test_load_corrupted_file_raises(self, tmp_path: Path) -> None:
        config_path = tmp_path / "config.toml"
        config_path.write_text("this is not valid toml {{{{")

        with pytest.raises(ChangelingConfigError, match="Failed to load"):
            load_config(config_path)
