from pathlib import Path

from click.testing import CliRunner

from imbue.changelings.core.zygote import ZYGOTE_CONFIG_FILENAME
from imbue.changelings.main import cli
from imbue.changelings.testing import init_and_commit_git_repo


def _create_git_zygote_repo(tmp_path: Path) -> Path:
    """Create a minimal git repo with a changeling.toml for testing."""
    repo_dir = tmp_path / "my-agent-repo"
    repo_dir.mkdir()
    (repo_dir / ZYGOTE_CONFIG_FILENAME).write_text(
        '[changeling]\nname = "test-bot"\ncommand = "python server.py"\nport = 9100\n'
    )
    init_and_commit_git_repo(repo_dir, tmp_path)
    return repo_dir


def _create_git_agent_type_repo(tmp_path: Path) -> Path:
    """Create a minimal git repo with an agent_type changeling.toml."""
    repo_dir = tmp_path / "elena-repo"
    repo_dir.mkdir()
    (repo_dir / ZYGOTE_CONFIG_FILENAME).write_text('[changeling]\nname = "elena-code"\nagent_type = "elena-code"\n')
    init_and_commit_git_repo(repo_dir, tmp_path)
    return repo_dir


def _data_dir_args(tmp_path: Path) -> list[str]:
    """Return the --data-dir CLI args pointing to a temp directory."""
    return ["--data-dir", str(tmp_path / "changelings-data")]


def test_deploy_fails_for_invalid_git_url(tmp_path: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["deploy", "/nonexistent/repo/path", *_data_dir_args(tmp_path)])

    assert result.exit_code != 0
    assert "git clone failed" in result.output


def test_deploy_fails_when_no_changeling_toml(tmp_path: Path) -> None:
    repo_dir = tmp_path / "empty-repo"
    repo_dir.mkdir()
    init_and_commit_git_repo(repo_dir, tmp_path, allow_empty=True)

    runner = CliRunner()
    result = runner.invoke(cli, ["deploy", str(repo_dir), *_data_dir_args(tmp_path)])

    assert result.exit_code != 0
    assert "changeling.toml" in result.output


def test_deploy_cleans_up_temp_dir_on_clone_failure(tmp_path: Path) -> None:
    """Verify that a failed clone does not leave temporary directories behind."""
    data_dir = tmp_path / "changelings-data"

    runner = CliRunner()
    runner.invoke(cli, ["deploy", "/nonexistent/repo/path", "--data-dir", str(data_dir)])

    if data_dir.exists():
        leftover = [p for p in data_dir.iterdir() if p.name.startswith(".tmp-")]
        assert leftover == []


def test_deploy_cleans_up_temp_dir_on_config_failure(tmp_path: Path) -> None:
    """Verify that a failed config load does not leave temporary directories behind."""
    repo_dir = tmp_path / "empty-repo"
    repo_dir.mkdir()
    init_and_commit_git_repo(repo_dir, tmp_path, allow_empty=True)
    data_dir = tmp_path / "changelings-data"

    runner = CliRunner()
    runner.invoke(cli, ["deploy", str(repo_dir), "--data-dir", str(data_dir)])

    leftover = [p for p in data_dir.iterdir() if p.name.startswith(".tmp-")]
    assert leftover == []


def test_deploy_stores_clone_under_agent_name(tmp_path: Path) -> None:
    """Verify that the clone is stored at <data-dir>/<agent-name>/."""
    repo_dir = _create_git_zygote_repo(tmp_path)
    data_dir = tmp_path / "changelings-data"

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "deploy",
            str(repo_dir),
            "--data-dir",
            str(data_dir),
            "--name",
            "my-bot",
            "--provider",
            "modal",
            "--no-self-deploy",
        ],
    )

    assert result.exit_code != 0
    assert "Only local deployment is supported" in result.output

    changeling_dir = data_dir / "my-bot"
    assert changeling_dir.is_dir()
    assert (changeling_dir / ZYGOTE_CONFIG_FILENAME).exists()


def test_deploy_rejects_modal_provider(tmp_path: Path) -> None:
    repo_dir = _create_git_zygote_repo(tmp_path)

    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["deploy", str(repo_dir), *_data_dir_args(tmp_path)],
        input="test-bot\n2\nN\n",
    )

    assert result.exit_code != 0
    assert "Only local deployment is supported" in result.output


def test_deploy_rejects_docker_provider(tmp_path: Path) -> None:
    repo_dir = _create_git_zygote_repo(tmp_path)

    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["deploy", str(repo_dir), *_data_dir_args(tmp_path)],
        input="test-bot\n3\nN\n",
    )

    assert result.exit_code != 0
    assert "Only local deployment is supported" in result.output


def test_deploy_shows_prompts(tmp_path: Path) -> None:
    """Verify all three prompts appear when deploying (using modal to abort before mng create)."""
    repo_dir = _create_git_zygote_repo(tmp_path)

    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["deploy", str(repo_dir), *_data_dir_args(tmp_path)],
        input="my-agent\n2\nN\n",
    )

    assert "What would you like to name this agent" in result.output
    assert "Where do you want to run" in result.output
    assert "launch its own agents" in result.output


def test_deploy_displays_clone_url(tmp_path: Path) -> None:
    repo_dir = _create_git_zygote_repo(tmp_path)

    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["deploy", str(repo_dir), *_data_dir_args(tmp_path)],
        input="test-bot\n2\nN\n",
    )

    assert "Cloning repository" in result.output


def test_deploy_name_flag_skips_prompt(tmp_path: Path) -> None:
    """Verify that --name skips the name prompt."""
    repo_dir = _create_git_zygote_repo(tmp_path)

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "deploy",
            str(repo_dir),
            "--name",
            "my-custom-name",
            "--provider",
            "modal",
            "--no-self-deploy",
            *_data_dir_args(tmp_path),
        ],
    )

    assert "What would you like to name this agent" not in result.output
    assert result.exit_code != 0
    assert "Only local deployment is supported" in result.output


def test_deploy_provider_flag_skips_prompt(tmp_path: Path) -> None:
    """Verify that --provider skips the provider prompt."""
    repo_dir = _create_git_zygote_repo(tmp_path)

    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["deploy", str(repo_dir), "--provider", "modal", "--no-self-deploy", *_data_dir_args(tmp_path)],
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
        cli,
        ["deploy", str(repo_dir), "--no-self-deploy", "--provider", "modal", *_data_dir_args(tmp_path)],
        input="test-bot\n",
    )

    assert "launch its own agents" not in result.output


def test_deploy_all_flags_skip_all_prompts(tmp_path: Path) -> None:
    """Verify that providing all flags skips all interactive prompts."""
    repo_dir = _create_git_zygote_repo(tmp_path)

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "deploy",
            str(repo_dir),
            "--name",
            "bot",
            "--provider",
            "modal",
            "--no-self-deploy",
            *_data_dir_args(tmp_path),
        ],
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
        cli,
        [
            "deploy",
            str(repo_dir),
            "--name",
            "test-elena",
            "--provider",
            "modal",
            "--no-self-deploy",
            *_data_dir_args(tmp_path),
        ],
    )

    assert "Deploying changeling from" in result.output
    assert result.exit_code != 0
    assert "Only local deployment is supported" in result.output


def test_deploy_rejects_duplicate_changeling_name(tmp_path: Path) -> None:
    """Verify that deploying with a name that already has a directory fails."""
    repo_dir = _create_git_zygote_repo(tmp_path)
    data_dir = tmp_path / "changelings-data"

    runner = CliRunner()
    result1 = runner.invoke(
        cli,
        [
            "deploy",
            str(repo_dir),
            "--name",
            "dup-bot",
            "--provider",
            "modal",
            "--no-self-deploy",
            "--data-dir",
            str(data_dir),
        ],
    )
    assert result1.exit_code != 0

    result2 = runner.invoke(
        cli,
        [
            "deploy",
            str(repo_dir),
            "--name",
            "dup-bot",
            "--provider",
            "modal",
            "--no-self-deploy",
            "--data-dir",
            str(data_dir),
        ],
    )
    assert result2.exit_code != 0
    assert "already exists" in result2.output
