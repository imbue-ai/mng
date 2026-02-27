import subprocess
from pathlib import Path

from click.testing import CliRunner

from imbue.changelings.cli.deploy import deploy
from imbue.changelings.core.zygote import ZYGOTE_CONFIG_FILENAME


def _create_git_zygote_repo(tmp_path: Path) -> Path:
    """Create a minimal git repo with a changeling.toml for testing."""
    repo_dir = tmp_path / "my-agent-repo"
    repo_dir.mkdir()
    config_file = repo_dir / ZYGOTE_CONFIG_FILENAME
    config_file.write_text('[changeling]\nname = "test-bot"\ncommand = "python server.py"\nport = 9100\n')
    subprocess.run(["git", "init"], cwd=repo_dir, check=True, capture_output=True)
    subprocess.run(["git", "add", "."], cwd=repo_dir, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "init"],
        cwd=repo_dir,
        check=True,
        capture_output=True,
        env={
            "GIT_AUTHOR_NAME": "test",
            "GIT_AUTHOR_EMAIL": "test@test",
            "GIT_COMMITTER_NAME": "test",
            "GIT_COMMITTER_EMAIL": "test@test",
            "HOME": str(tmp_path),
            "PATH": "/usr/bin:/bin:/usr/local/bin",
        },
    )
    return repo_dir


def _create_git_agent_type_repo(tmp_path: Path) -> Path:
    """Create a minimal git repo with an agent_type changeling.toml."""
    repo_dir = tmp_path / "elena-repo"
    repo_dir.mkdir()
    config_file = repo_dir / ZYGOTE_CONFIG_FILENAME
    config_file.write_text('[changeling]\nname = "elena-code"\nagent_type = "elena-code"\n')
    subprocess.run(["git", "init"], cwd=repo_dir, check=True, capture_output=True)
    subprocess.run(["git", "add", "."], cwd=repo_dir, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "init"],
        cwd=repo_dir,
        check=True,
        capture_output=True,
        env={
            "GIT_AUTHOR_NAME": "test",
            "GIT_AUTHOR_EMAIL": "test@test",
            "GIT_COMMITTER_NAME": "test",
            "GIT_COMMITTER_EMAIL": "test@test",
            "HOME": str(tmp_path),
            "PATH": "/usr/bin:/bin:/usr/local/bin",
        },
    )
    return repo_dir


def _create_git_repo_with_subpath(tmp_path: Path) -> Path:
    """Create a git repo where the changeling.toml is in a subdirectory."""
    repo_dir = tmp_path / "multi-agent-repo"
    repo_dir.mkdir()
    sub_dir = repo_dir / "agents" / "my-agent"
    sub_dir.mkdir(parents=True)
    config_file = sub_dir / ZYGOTE_CONFIG_FILENAME
    config_file.write_text('[changeling]\nname = "sub-bot"\ncommand = "python server.py"\nport = 9200\n')
    subprocess.run(["git", "init"], cwd=repo_dir, check=True, capture_output=True)
    subprocess.run(["git", "add", "."], cwd=repo_dir, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "init"],
        cwd=repo_dir,
        check=True,
        capture_output=True,
        env={
            "GIT_AUTHOR_NAME": "test",
            "GIT_AUTHOR_EMAIL": "test@test",
            "GIT_COMMITTER_NAME": "test",
            "GIT_COMMITTER_EMAIL": "test@test",
            "HOME": str(tmp_path),
            "PATH": "/usr/bin:/bin:/usr/local/bin",
        },
    )
    return repo_dir


def test_deploy_fails_for_invalid_git_url() -> None:
    runner = CliRunner()
    result = runner.invoke(deploy, ["/nonexistent/repo/path"])

    assert result.exit_code != 0
    assert "git clone failed" in result.output


def test_deploy_fails_when_no_changeling_toml(tmp_path: Path) -> None:
    repo_dir = tmp_path / "empty-repo"
    repo_dir.mkdir()
    subprocess.run(["git", "init"], cwd=repo_dir, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "--allow-empty", "-m", "init"],
        cwd=repo_dir,
        check=True,
        capture_output=True,
        env={
            "GIT_AUTHOR_NAME": "test",
            "GIT_AUTHOR_EMAIL": "test@test",
            "GIT_COMMITTER_NAME": "test",
            "GIT_COMMITTER_EMAIL": "test@test",
            "HOME": str(tmp_path),
            "PATH": "/usr/bin:/bin:/usr/local/bin",
        },
    )

    runner = CliRunner()
    result = runner.invoke(deploy, [str(repo_dir)])

    assert result.exit_code != 0
    assert "changeling.toml" in result.output


def test_deploy_rejects_modal_provider(tmp_path: Path) -> None:
    repo_dir = _create_git_zygote_repo(tmp_path)

    runner = CliRunner()
    result = runner.invoke(deploy, [str(repo_dir)], input="test-bot\n2\nN\n")

    assert result.exit_code != 0
    assert "Only local deployment is supported" in result.output


def test_deploy_rejects_docker_provider(tmp_path: Path) -> None:
    repo_dir = _create_git_zygote_repo(tmp_path)

    runner = CliRunner()
    result = runner.invoke(deploy, [str(repo_dir)], input="test-bot\n3\nN\n")

    assert result.exit_code != 0
    assert "Only local deployment is supported" in result.output


def test_deploy_shows_prompts(tmp_path: Path) -> None:
    """Verify all three prompts appear when deploying (using modal to abort before mng create)."""
    repo_dir = _create_git_zygote_repo(tmp_path)

    runner = CliRunner()
    result = runner.invoke(deploy, [str(repo_dir)], input="my-agent\n2\nN\n")

    assert "What would you like to name this agent" in result.output
    assert "Where do you want to run" in result.output
    assert "launch its own agents" in result.output


def test_deploy_displays_clone_url(tmp_path: Path) -> None:
    repo_dir = _create_git_zygote_repo(tmp_path)

    runner = CliRunner()
    result = runner.invoke(deploy, [str(repo_dir)], input="test-bot\n2\nN\n")

    assert "Cloning repository" in result.output


def test_deploy_name_flag_skips_prompt(tmp_path: Path) -> None:
    """Verify that --name skips the name prompt."""
    repo_dir = _create_git_zygote_repo(tmp_path)

    runner = CliRunner()
    result = runner.invoke(
        deploy,
        [str(repo_dir), "--name", "my-custom-name", "--provider", "modal", "--no-self-deploy"],
    )

    assert "What would you like to name this agent" not in result.output
    assert result.exit_code != 0
    assert "Only local deployment is supported" in result.output


def test_deploy_provider_flag_skips_prompt(tmp_path: Path) -> None:
    """Verify that --provider skips the provider prompt."""
    repo_dir = _create_git_zygote_repo(tmp_path)

    runner = CliRunner()
    result = runner.invoke(
        deploy,
        [str(repo_dir), "--provider", "modal", "--no-self-deploy"],
        input="test-bot\n",
    )

    assert "Where do you want to run" not in result.output
    assert result.exit_code != 0
    assert "Only local deployment is supported" in result.output


def test_deploy_self_deploy_flag_skips_prompt(tmp_path: Path) -> None:
    """Verify that --no-self-deploy skips the self-deploy prompt."""
    repo_dir = _create_git_zygote_repo(tmp_path)

    runner = CliRunner()
    result = runner.invoke(
        deploy,
        [str(repo_dir), "--no-self-deploy", "--provider", "modal"],
        input="test-bot\n",
    )

    assert "launch its own agents" not in result.output


def test_deploy_all_flags_skip_all_prompts(tmp_path: Path) -> None:
    """Verify that providing all flags skips all interactive prompts."""
    repo_dir = _create_git_zygote_repo(tmp_path)

    runner = CliRunner()
    result = runner.invoke(
        deploy,
        [str(repo_dir), "--name", "bot", "--provider", "modal", "--no-self-deploy"],
    )

    assert "What would you like to name this agent" not in result.output
    assert "Where do you want to run" not in result.output
    assert "launch its own agents" not in result.output
    assert result.exit_code != 0
    assert "Only local deployment is supported" in result.output


def test_deploy_loads_agent_type_zygote(tmp_path: Path) -> None:
    """Verify that a zygote with agent_type is loaded correctly."""
    repo_dir = _create_git_agent_type_repo(tmp_path)

    runner = CliRunner()
    result = runner.invoke(
        deploy,
        [str(repo_dir), "--name", "test-elena", "--provider", "modal", "--no-self-deploy"],
    )

    assert "Deploying changeling from" in result.output
    assert result.exit_code != 0
    assert "Only local deployment is supported" in result.output


def test_deploy_with_repo_sub_path(tmp_path: Path) -> None:
    """Verify that --repo-sub-path correctly finds the changeling.toml in a subdirectory."""
    repo_dir = _create_git_repo_with_subpath(tmp_path)

    runner = CliRunner()
    result = runner.invoke(
        deploy,
        [
            str(repo_dir),
            "--repo-sub-path",
            "agents/my-agent",
            "--name",
            "sub-bot",
            "--provider",
            "modal",
            "--no-self-deploy",
        ],
    )

    assert "Deploying changeling from" in result.output
    assert result.exit_code != 0
    assert "Only local deployment is supported" in result.output


def test_deploy_with_invalid_repo_sub_path(tmp_path: Path) -> None:
    """Verify that --repo-sub-path fails when the subdirectory does not exist."""
    repo_dir = _create_git_zygote_repo(tmp_path)

    runner = CliRunner()
    result = runner.invoke(
        deploy,
        [
            str(repo_dir),
            "--repo-sub-path",
            "nonexistent/path",
            "--name",
            "bot",
            "--provider",
            "local",
            "--no-self-deploy",
        ],
    )

    assert result.exit_code != 0
    assert "not found in cloned repository" in result.output
