from pathlib import Path
from unittest.mock import patch

from click.testing import CliRunner

from imbue.changelings.config import add_changeling
from imbue.changelings.config import load_config
from imbue.changelings.config import save_config
from imbue.changelings.conftest import make_test_definition as _make_definition
from imbue.changelings.data_types import ChangelingConfig
from imbue.changelings.data_types import ChangelingDefinition
from imbue.changelings.main import cli
from imbue.changelings.primitives import ChangelingName


def _save_fixture_config(config_path: Path, *definitions: ChangelingDefinition) -> None:
    config = ChangelingConfig()
    for defn in definitions:
        config = add_changeling(config, defn)
    save_config(config, config_path)


class TestAddCommand:
    def test_add_new_changeling(self, tmp_path: Path) -> None:
        config_path = tmp_path / "config.toml"
        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "add",
                "my-fairy",
                "--template",
                "fixme-fairy",
                "--repo",
                "git@github.com:org/repo.git",
                "--schedule",
                "0 3 * * *",
                "--config-path",
                str(config_path),
            ],
        )

        assert result.exit_code == 0, result.output
        assert "Registered changeling 'my-fairy'" in result.output

        config = load_config(config_path)
        assert ChangelingName("my-fairy") in config.changeling_by_name

    def test_add_duplicate_fails(self, tmp_path: Path) -> None:
        config_path = tmp_path / "config.toml"
        _save_fixture_config(config_path, _make_definition("existing"))

        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "add",
                "existing",
                "--template",
                "fixme-fairy",
                "--repo",
                "git@github.com:org/repo.git",
                "--schedule",
                "0 3 * * *",
                "--config-path",
                str(config_path),
            ],
        )

        assert result.exit_code != 0
        assert "already exists" in result.output

    def test_add_with_custom_branch(self, tmp_path: Path) -> None:
        config_path = tmp_path / "config.toml"
        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "add",
                "dev-fairy",
                "--template",
                "fixme-fairy",
                "--repo",
                "git@github.com:org/repo.git",
                "--schedule",
                "0 3 * * *",
                "--branch",
                "develop",
                "--config-path",
                str(config_path),
            ],
        )

        assert result.exit_code == 0, result.output
        config = load_config(config_path)
        assert config.changeling_by_name[ChangelingName("dev-fairy")].branch == "develop"

    def test_add_disabled(self, tmp_path: Path) -> None:
        config_path = tmp_path / "config.toml"
        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "add",
                "disabled-fairy",
                "--template",
                "fixme-fairy",
                "--repo",
                "git@github.com:org/repo.git",
                "--schedule",
                "0 3 * * *",
                "--disabled",
                "--config-path",
                str(config_path),
            ],
        )

        assert result.exit_code == 0, result.output
        config = load_config(config_path)
        assert config.changeling_by_name[ChangelingName("disabled-fairy")].is_enabled is False

    def test_add_unknown_template_warns(self, tmp_path: Path) -> None:
        config_path = tmp_path / "config.toml"
        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "add",
                "custom",
                "--template",
                "unknown-template",
                "--repo",
                "git@github.com:org/repo.git",
                "--schedule",
                "0 3 * * *",
                "--config-path",
                str(config_path),
            ],
        )

        assert result.exit_code == 0, result.output
        assert "not a known built-in template" in result.output


class TestListCommand:
    def test_list_empty(self, tmp_path: Path) -> None:
        config_path = tmp_path / "config.toml"
        runner = CliRunner()
        result = runner.invoke(cli, ["list", "--config-path", str(config_path)])

        assert result.exit_code == 0
        assert "No changelings registered" in result.output

    def test_list_with_changelings(self, tmp_path: Path) -> None:
        config_path = tmp_path / "config.toml"
        _save_fixture_config(
            config_path,
            _make_definition("fairy-1", template="fixme-fairy"),
            _make_definition("guardian-1", template="code-guardian"),
        )

        runner = CliRunner()
        result = runner.invoke(cli, ["list", "--config-path", str(config_path)])

        assert result.exit_code == 0
        assert "fairy-1" in result.output
        assert "guardian-1" in result.output
        assert "fixme-fairy" in result.output
        assert "code-guardian" in result.output

    def test_list_hides_disabled_by_default(self, tmp_path: Path) -> None:
        config_path = tmp_path / "config.toml"
        _save_fixture_config(
            config_path,
            _make_definition("enabled-one"),
            _make_definition("disabled-one", is_enabled=False),
        )

        runner = CliRunner()
        result = runner.invoke(cli, ["list", "--config-path", str(config_path)])

        assert result.exit_code == 0
        assert "enabled-one" in result.output
        assert "disabled-one" not in result.output

    def test_list_all_shows_disabled(self, tmp_path: Path) -> None:
        config_path = tmp_path / "config.toml"
        _save_fixture_config(
            config_path,
            _make_definition("enabled-one"),
            _make_definition("disabled-one", is_enabled=False),
        )

        runner = CliRunner()
        result = runner.invoke(cli, ["list", "--all", "--config-path", str(config_path)])

        assert result.exit_code == 0
        assert "enabled-one" in result.output
        assert "disabled-one" in result.output

    def test_list_json_format(self, tmp_path: Path) -> None:
        config_path = tmp_path / "config.toml"
        _save_fixture_config(config_path, _make_definition("my-fairy"))

        runner = CliRunner()
        result = runner.invoke(cli, ["list", "--format", "json", "--config-path", str(config_path)])

        assert result.exit_code == 0
        import json

        data = json.loads(result.output)
        assert len(data) == 1
        assert data[0]["name"] == "my-fairy"
        assert data[0]["template"] == "fixme-fairy"

    def test_list_json_empty(self, tmp_path: Path) -> None:
        config_path = tmp_path / "config.toml"
        runner = CliRunner()
        result = runner.invoke(cli, ["list", "--format", "json", "--config-path", str(config_path)])

        assert result.exit_code == 0
        import json

        data = json.loads(result.output)
        assert data == []


class TestRunCommand:
    def test_run_without_local_fails(self, tmp_path: Path) -> None:
        config_path = tmp_path / "config.toml"
        _save_fixture_config(config_path, _make_definition("my-fairy"))

        runner = CliRunner()
        result = runner.invoke(cli, ["run", "my-fairy", "--config-path", str(config_path)])

        assert result.exit_code != 0
        assert "Modal execution is not yet implemented" in result.output

    def test_run_nonexistent_changeling_fails(self, tmp_path: Path) -> None:
        config_path = tmp_path / "config.toml"
        _save_fixture_config(config_path, _make_definition("existing"))

        runner = CliRunner()
        result = runner.invoke(cli, ["run", "nonexistent", "--local", "--config-path", str(config_path)])

        assert result.exit_code != 0

    def test_run_local_calls_subprocess(self, tmp_path: Path) -> None:
        config_path = tmp_path / "config.toml"
        _save_fixture_config(config_path, _make_definition("my-fairy"))

        runner = CliRunner()
        with patch("imbue.changelings.cli.run.subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            result = runner.invoke(cli, ["run", "my-fairy", "--local", "--config-path", str(config_path)])

        assert result.exit_code == 0, result.output
        assert "Running changeling 'my-fairy' locally" in result.output
        assert "completed successfully" in result.output

        mock_run.assert_called_once()
        call_args = mock_run.call_args[0][0]
        assert call_args[:4] == ["uv", "run", "mngr", "create"]
        assert "claude" in call_args
        assert "--worktree" in call_args
        assert "--no-connect" in call_args
        assert "--await-agent-stopped" in call_args

    def test_run_local_failure_exits_nonzero(self, tmp_path: Path) -> None:
        config_path = tmp_path / "config.toml"
        _save_fixture_config(config_path, _make_definition("my-fairy"))

        runner = CliRunner()
        with patch("imbue.changelings.cli.run.subprocess.run") as mock_run:
            mock_run.return_value.returncode = 1
            result = runner.invoke(cli, ["run", "my-fairy", "--local", "--config-path", str(config_path)])

        assert result.exit_code != 0

    def test_run_disabled_changeling_warns(self, tmp_path: Path) -> None:
        config_path = tmp_path / "config.toml"
        _save_fixture_config(config_path, _make_definition("disabled-one", is_enabled=False))

        runner = CliRunner()
        with patch("imbue.changelings.cli.run.subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            result = runner.invoke(cli, ["run", "disabled-one", "--local", "--config-path", str(config_path)])

        assert result.exit_code == 0, result.output
        assert "disabled" in result.output

    def test_run_uses_custom_message_when_set(self, tmp_path: Path) -> None:
        config_path = tmp_path / "config.toml"
        _save_fixture_config(config_path, _make_definition("custom", message="do this specific thing"))

        runner = CliRunner()
        with patch("imbue.changelings.cli.run.subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            result = runner.invoke(cli, ["run", "custom", "--local", "--config-path", str(config_path)])

        assert result.exit_code == 0, result.output
        call_args = mock_run.call_args[0][0]
        msg_idx = call_args.index("--message")
        assert call_args[msg_idx + 1] == "do this specific thing"

    def test_run_uses_template_message_when_no_custom(self, tmp_path: Path) -> None:
        config_path = tmp_path / "config.toml"
        _save_fixture_config(config_path, _make_definition("guardian", template="code-guardian"))

        runner = CliRunner()
        with patch("imbue.changelings.cli.run.subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            result = runner.invoke(cli, ["run", "guardian", "--local", "--config-path", str(config_path)])

        assert result.exit_code == 0, result.output
        call_args = mock_run.call_args[0][0]
        msg_idx = call_args.index("--message")
        assert "inconsistencies" in call_args[msg_idx + 1].lower()

    def test_run_includes_env_vars(self, tmp_path: Path) -> None:
        config_path = tmp_path / "config.toml"
        _save_fixture_config(
            config_path,
            _make_definition("with-env", env_vars={"MY_KEY": "my_value"}),
        )

        runner = CliRunner()
        with patch("imbue.changelings.cli.run.subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            result = runner.invoke(cli, ["run", "with-env", "--local", "--config-path", str(config_path)])

        assert result.exit_code == 0, result.output
        call_args = mock_run.call_args[0][0]
        env_idx = call_args.index("--env")
        assert call_args[env_idx + 1] == "MY_KEY=my_value"

    def test_run_includes_extra_mngr_args(self, tmp_path: Path) -> None:
        config_path = tmp_path / "config.toml"
        _save_fixture_config(
            config_path,
            _make_definition("with-args", extra_mngr_args="--timeout 300"),
        )

        runner = CliRunner()
        with patch("imbue.changelings.cli.run.subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            result = runner.invoke(cli, ["run", "with-args", "--local", "--config-path", str(config_path)])

        assert result.exit_code == 0, result.output
        call_args = mock_run.call_args[0][0]
        assert "--timeout" in call_args
        assert "300" in call_args


class TestBuildMngrCreateArgs:
    def test_basic_args(self) -> None:
        from imbue.changelings.cli.run import build_mngr_create_args

        defn = _make_definition("my-fairy")
        args = build_mngr_create_args(defn, "20260101-120000")

        assert args[:4] == ["uv", "run", "mngr", "create"]
        assert "changeling-my-fairy-20260101-120000" in args
        assert "claude" in args
        assert "--worktree" in args
        assert "--base-branch" in args
        assert "main" in args
        assert "--new-branch" in args
        assert "changeling/my-fairy-20260101-120000" in args
        assert "--no-connect" in args
        assert "--await-agent-stopped" in args
        assert "--no-ensure-clean" in args
        assert "--message" in args

    def test_custom_agent_type(self) -> None:
        from imbue.changelings.cli.run import build_mngr_create_args

        defn = _make_definition("my-fairy", agent_type="opencode")
        args = build_mngr_create_args(defn, "20260101-120000")

        assert "opencode" in args
        assert "claude" not in args

    def test_custom_branch(self) -> None:
        from imbue.changelings.cli.run import build_mngr_create_args

        defn = _make_definition("my-fairy", branch="develop")
        args = build_mngr_create_args(defn, "20260101-120000")

        base_idx = args.index("--base-branch")
        assert args[base_idx + 1] == "develop"

    def test_env_vars_appended(self) -> None:
        from imbue.changelings.cli.run import build_mngr_create_args

        defn = _make_definition("my-fairy", env_vars={"A": "1", "B": "2"})
        args = build_mngr_create_args(defn, "20260101-120000")

        env_indices = [i for i, a in enumerate(args) if a == "--env"]
        assert len(env_indices) == 2

    def test_extra_mngr_args_appended(self) -> None:
        from imbue.changelings.cli.run import build_mngr_create_args

        defn = _make_definition("my-fairy", extra_mngr_args="--timeout 300 --depth 1")
        args = build_mngr_create_args(defn, "20260101-120000")

        assert "--timeout" in args
        assert "300" in args
        assert "--depth" in args
        assert "1" in args
