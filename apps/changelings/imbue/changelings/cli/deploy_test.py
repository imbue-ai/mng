from pathlib import Path

from click.testing import CliRunner

from imbue.changelings.cli.deploy import deploy
from imbue.changelings.core.zygote import ZYGOTE_CONFIG_FILENAME


def _create_zygote_dir(tmp_path: Path) -> Path:
    zygote_dir = tmp_path / "my-agent"
    zygote_dir.mkdir()
    config_file = zygote_dir / ZYGOTE_CONFIG_FILENAME
    config_file.write_text('[changeling]\nname = "test-bot"\ncommand = "python server.py"\nport = 9100\n')
    return zygote_dir


def test_deploy_fails_for_nonexistent_path() -> None:
    runner = CliRunner()
    result = runner.invoke(deploy, ["/nonexistent/path"])

    assert result.exit_code != 0


def test_deploy_fails_when_no_changeling_toml(tmp_path: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(deploy, [str(tmp_path)])

    assert result.exit_code != 0
    assert "changeling.toml" in result.output


def test_deploy_rejects_modal_provider(tmp_path: Path) -> None:
    zygote_dir = _create_zygote_dir(tmp_path)

    runner = CliRunner()
    result = runner.invoke(deploy, [str(zygote_dir)], input="test-bot\n2\nN\n")

    assert result.exit_code != 0
    assert "Only local deployment is supported" in result.output


def test_deploy_rejects_docker_provider(tmp_path: Path) -> None:
    zygote_dir = _create_zygote_dir(tmp_path)

    runner = CliRunner()
    result = runner.invoke(deploy, [str(zygote_dir)], input="test-bot\n3\nN\n")

    assert result.exit_code != 0
    assert "Only local deployment is supported" in result.output


def test_deploy_shows_prompts(tmp_path: Path) -> None:
    """Verify all three prompts appear when deploying (using modal to abort before mng create)."""
    zygote_dir = _create_zygote_dir(tmp_path)

    runner = CliRunner()
    result = runner.invoke(deploy, [str(zygote_dir)], input="my-agent\n2\nN\n")

    assert "What would you like to name this agent" in result.output
    assert "Where do you want to run" in result.output
    assert "launch its own agents" in result.output


def test_deploy_displays_zygote_path(tmp_path: Path) -> None:
    zygote_dir = _create_zygote_dir(tmp_path)

    runner = CliRunner()
    result = runner.invoke(deploy, [str(zygote_dir)], input="test-bot\n2\nN\n")

    assert "Deploying changeling from" in result.output
