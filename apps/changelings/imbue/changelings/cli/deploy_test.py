from pathlib import Path
from unittest.mock import patch

from click.testing import CliRunner

from imbue.changelings.cli.deploy import deploy
from imbue.changelings.core.zygote import ZYGOTE_CONFIG_FILENAME
from imbue.changelings.deployment.local import DeploymentResult
from imbue.mng.primitives import AgentId


def _create_zygote_dir(tmp_path: Path) -> Path:
    zygote_dir = tmp_path / "my-agent"
    zygote_dir.mkdir()
    config_file = zygote_dir / ZYGOTE_CONFIG_FILENAME
    config_file.write_text('[changeling]\nname = "test-bot"\ncommand = "python server.py"\nport = 9100\n')
    return zygote_dir


def _mock_deploy_result() -> DeploymentResult:
    return DeploymentResult(
        agent_name="test-bot",
        changeling_id=AgentId("agent-00000000000000000000000000000001"),
        backend_url="http://127.0.0.1:9100",
        login_url="http://127.0.0.1:8420/login?agent_id=test&one_time_code=abc",
    )


def test_deploy_fails_for_nonexistent_path() -> None:
    runner = CliRunner()
    result = runner.invoke(deploy, ["/nonexistent/path"])

    assert result.exit_code != 0


def test_deploy_fails_when_no_changeling_toml(tmp_path: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(deploy, [str(tmp_path)])

    assert result.exit_code != 0
    assert "changeling.toml" in result.output


def test_deploy_shows_zygote_info(tmp_path: Path) -> None:
    zygote_dir = _create_zygote_dir(tmp_path)

    with patch(
        "imbue.changelings.cli.deploy.deploy_local",
        return_value=_mock_deploy_result(),
    ):
        with patch("imbue.changelings.cli.deploy.start_forwarding_server"):
            runner = CliRunner()
            result = runner.invoke(deploy, [str(zygote_dir)], input="test-bot\n1\nN\n")

    assert "Deploying changeling from" in result.output


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


def test_deploy_prompts_for_name_and_provider(tmp_path: Path) -> None:
    zygote_dir = _create_zygote_dir(tmp_path)

    with patch(
        "imbue.changelings.cli.deploy.deploy_local",
        return_value=_mock_deploy_result(),
    ):
        with patch("imbue.changelings.cli.deploy.start_forwarding_server"):
            runner = CliRunner()
            result = runner.invoke(deploy, [str(zygote_dir)], input="\n1\nN\n")

    assert "What would you like to name this agent" in result.output
    assert "Where do you want to run" in result.output


def test_deploy_prompts_for_self_deploy(tmp_path: Path) -> None:
    zygote_dir = _create_zygote_dir(tmp_path)

    with patch(
        "imbue.changelings.cli.deploy.deploy_local",
        return_value=_mock_deploy_result(),
    ):
        with patch("imbue.changelings.cli.deploy.start_forwarding_server"):
            runner = CliRunner()
            result = runner.invoke(deploy, [str(zygote_dir)], input="test-bot\n1\nN\n")

    assert "launch its own agents" in result.output


def test_deploy_prints_success_info(tmp_path: Path) -> None:
    zygote_dir = _create_zygote_dir(tmp_path)

    with patch(
        "imbue.changelings.cli.deploy.deploy_local",
        return_value=_mock_deploy_result(),
    ):
        with patch("imbue.changelings.cli.deploy.start_forwarding_server"):
            runner = CliRunner()
            result = runner.invoke(deploy, [str(zygote_dir)], input="test-bot\n1\nN\n")

    assert "Changeling deployed successfully" in result.output
    assert "test-bot" in result.output
    assert "Login URL" in result.output
