import subprocess
from pathlib import Path

from click.testing import CliRunner

from imbue.changelings.cli.deploy import _MNG_SETTINGS_REL_PATH
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


# --- Tests for --agent-type (no git URL) ---


def test_deploy_agent_type_creates_repo_with_changeling_toml(tmp_path: Path) -> None:
    """Verify that --agent-type creates a changeling.toml with the correct agent_type."""
    data_dir = tmp_path / "changelings-data"

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "deploy",
            "--agent-type",
            "elena-code",
            "--name",
            "my-elena",
            "--provider",
            "modal",
            "--no-self-deploy",
            "--data-dir",
            str(data_dir),
        ],
    )

    assert result.exit_code != 0
    assert "Only local deployment is supported" in result.output

    changeling_dir = data_dir / "my-elena"
    assert changeling_dir.is_dir()

    config_content = (changeling_dir / ZYGOTE_CONFIG_FILENAME).read_text()
    assert 'agent_type = "elena-code"' in config_content
    assert 'name = "elena-code"' in config_content


def test_deploy_agent_type_creates_mng_settings_toml(tmp_path: Path) -> None:
    """Verify that --agent-type creates .mng/settings.toml with the correct template."""
    data_dir = tmp_path / "changelings-data"

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "deploy",
            "--agent-type",
            "elena-code",
            "--name",
            "my-elena",
            "--provider",
            "modal",
            "--no-self-deploy",
            "--data-dir",
            str(data_dir),
        ],
    )

    assert result.exit_code != 0
    assert "Only local deployment is supported" in result.output

    settings_path = data_dir / "my-elena" / _MNG_SETTINGS_REL_PATH
    assert settings_path.exists()

    settings_content = settings_path.read_text()
    assert "[create_templates.entrypoint]" in settings_content
    assert 'agent_type = "elena-code"' in settings_content


def test_deploy_agent_type_creates_git_repo_with_commit(tmp_path: Path) -> None:
    """Verify that --agent-type creates a git repo with an initial commit."""
    data_dir = tmp_path / "changelings-data"

    runner = CliRunner()
    runner.invoke(
        cli,
        [
            "deploy",
            "--agent-type",
            "elena-code",
            "--name",
            "my-elena",
            "--provider",
            "modal",
            "--no-self-deploy",
            "--data-dir",
            str(data_dir),
        ],
    )

    changeling_dir = data_dir / "my-elena"
    assert (changeling_dir / ".git").is_dir()

    # Verify there is at least one commit
    log_result = subprocess.run(
        ["git", "log", "--oneline"],
        cwd=changeling_dir,
        capture_output=True,
        text=True,
    )
    assert log_result.returncode == 0
    assert "Initial changeling setup" in log_result.stdout


def test_deploy_agent_type_defaults_name_to_agent_type(tmp_path: Path) -> None:
    """Verify that --agent-type defaults the agent name prompt to the agent type value."""
    data_dir = tmp_path / "changelings-data"

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "deploy",
            "--agent-type",
            "elena-code",
            "--provider",
            "modal",
            "--no-self-deploy",
            "--data-dir",
            str(data_dir),
        ],
        input="elena-code\n",
    )

    assert "elena-code" in result.output
    changeling_dir = data_dir / "elena-code"
    assert changeling_dir.is_dir()


def test_deploy_fails_without_git_url_or_agent_type(tmp_path: Path) -> None:
    """Verify that deploy fails when neither GIT_URL nor --agent-type is provided."""
    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["deploy", *_data_dir_args(tmp_path)],
    )

    assert result.exit_code != 0
    assert "Either GIT_URL or --agent-type must be provided" in result.output


def test_deploy_agent_type_shows_creating_message(tmp_path: Path) -> None:
    """Verify that --agent-type shows a 'Creating changeling repo' message instead of 'Cloning'."""
    data_dir = tmp_path / "changelings-data"

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "deploy",
            "--agent-type",
            "elena-code",
            "--name",
            "test-bot",
            "--provider",
            "modal",
            "--no-self-deploy",
            "--data-dir",
            str(data_dir),
        ],
    )

    assert "Cloning repository" not in result.output
    assert "Deploying changeling from" in result.output


# --- Tests for --add-path ---


def test_deploy_add_path_copies_file_into_repo(tmp_path: Path) -> None:
    """Verify that --add-path copies a file into the cloned repo."""
    repo_dir = _create_git_zygote_repo(tmp_path)
    data_dir = tmp_path / "changelings-data"

    # Create a source file to add
    extra_file = tmp_path / "extra.txt"
    extra_file.write_text("extra content")

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "deploy",
            str(repo_dir),
            "--add-path",
            "{}:extra.txt".format(extra_file),
            "--name",
            "add-path-bot",
            "--provider",
            "modal",
            "--no-self-deploy",
            "--data-dir",
            str(data_dir),
        ],
    )

    assert result.exit_code != 0
    assert "Only local deployment is supported" in result.output

    changeling_dir = data_dir / "add-path-bot"
    assert (changeling_dir / "extra.txt").read_text() == "extra content"


def test_deploy_add_path_copies_directory_into_repo(tmp_path: Path) -> None:
    """Verify that --add-path recursively copies a directory into the repo."""
    repo_dir = _create_git_zygote_repo(tmp_path)
    data_dir = tmp_path / "changelings-data"

    # Create a source directory to add
    src_dir = tmp_path / "src-config"
    src_dir.mkdir()
    (src_dir / "a.txt").write_text("file a")
    sub = src_dir / "sub"
    sub.mkdir()
    (sub / "b.txt").write_text("file b")

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "deploy",
            str(repo_dir),
            "--add-path",
            "{}:config".format(src_dir),
            "--name",
            "dir-bot",
            "--provider",
            "modal",
            "--no-self-deploy",
            "--data-dir",
            str(data_dir),
        ],
    )

    assert result.exit_code != 0

    changeling_dir = data_dir / "dir-bot"
    assert (changeling_dir / "config" / "a.txt").read_text() == "file a"
    assert (changeling_dir / "config" / "sub" / "b.txt").read_text() == "file b"


def test_deploy_add_path_with_agent_type(tmp_path: Path) -> None:
    """Verify that --add-path works with --agent-type (no git URL)."""
    data_dir = tmp_path / "changelings-data"

    extra_file = tmp_path / "my-config.json"
    extra_file.write_text('{"key": "value"}')

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "deploy",
            "--agent-type",
            "elena-code",
            "--add-path",
            "{}:config/my-config.json".format(extra_file),
            "--name",
            "path-elena",
            "--provider",
            "modal",
            "--no-self-deploy",
            "--data-dir",
            str(data_dir),
        ],
    )

    assert result.exit_code != 0
    assert "Only local deployment is supported" in result.output

    changeling_dir = data_dir / "path-elena"
    assert (changeling_dir / "config" / "my-config.json").read_text() == '{"key": "value"}'
    assert (changeling_dir / ZYGOTE_CONFIG_FILENAME).exists()
    assert (changeling_dir / _MNG_SETTINGS_REL_PATH).exists()


def test_deploy_add_path_multiple_paths(tmp_path: Path) -> None:
    """Verify that multiple --add-path args are all copied."""
    data_dir = tmp_path / "changelings-data"

    file_a = tmp_path / "a.txt"
    file_a.write_text("aaa")
    file_b = tmp_path / "b.txt"
    file_b.write_text("bbb")

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "deploy",
            "--agent-type",
            "elena-code",
            "--add-path",
            "{}:a.txt".format(file_a),
            "--add-path",
            "{}:b.txt".format(file_b),
            "--name",
            "multi-bot",
            "--provider",
            "modal",
            "--no-self-deploy",
            "--data-dir",
            str(data_dir),
        ],
    )

    assert result.exit_code != 0

    changeling_dir = data_dir / "multi-bot"
    assert (changeling_dir / "a.txt").read_text() == "aaa"
    assert (changeling_dir / "b.txt").read_text() == "bbb"


def test_deploy_add_path_fails_for_nonexistent_source(tmp_path: Path) -> None:
    """Verify that --add-path fails when the source path does not exist."""
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "deploy",
            "--agent-type",
            "elena-code",
            "--add-path",
            "/nonexistent/path:dest.txt",
            "--name",
            "bad-bot",
            "--provider",
            "modal",
            "--no-self-deploy",
            *_data_dir_args(tmp_path),
        ],
    )

    assert result.exit_code != 0
    assert "does not exist" in result.output


def test_deploy_add_path_fails_for_invalid_format(tmp_path: Path) -> None:
    """Verify that --add-path fails when the format is not SRC:DEST."""
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "deploy",
            "--agent-type",
            "elena-code",
            "--add-path",
            "no-colon-here",
            "--name",
            "bad-bot",
            "--provider",
            "modal",
            "--no-self-deploy",
            *_data_dir_args(tmp_path),
        ],
    )

    assert result.exit_code != 0
    assert "SRC:DEST" in result.output


def test_deploy_add_path_fails_for_absolute_dest(tmp_path: Path) -> None:
    """Verify that --add-path fails when DEST is an absolute path."""
    extra_file = tmp_path / "file.txt"
    extra_file.write_text("content")

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "deploy",
            "--agent-type",
            "elena-code",
            "--add-path",
            "{}:/absolute/dest.txt".format(extra_file),
            "--name",
            "bad-bot",
            "--provider",
            "modal",
            "--no-self-deploy",
            *_data_dir_args(tmp_path),
        ],
    )

    assert result.exit_code != 0
    assert "must be relative" in result.output


def test_deploy_add_path_files_are_committed(tmp_path: Path) -> None:
    """Verify that --add-path files are included in the git commit."""
    data_dir = tmp_path / "changelings-data"

    extra_file = tmp_path / "extra.txt"
    extra_file.write_text("committed content")

    runner = CliRunner()
    runner.invoke(
        cli,
        [
            "deploy",
            "--agent-type",
            "elena-code",
            "--add-path",
            "{}:extra.txt".format(extra_file),
            "--name",
            "commit-bot",
            "--provider",
            "modal",
            "--no-self-deploy",
            "--data-dir",
            str(data_dir),
        ],
    )

    changeling_dir = data_dir / "commit-bot"

    # Verify that the extra file is tracked in git
    ls_result = subprocess.run(
        ["git", "ls-files"],
        cwd=changeling_dir,
        capture_output=True,
        text=True,
    )
    assert "extra.txt" in ls_result.stdout


def test_deploy_add_path_with_clone_commits_added_files(tmp_path: Path) -> None:
    """Verify that --add-path files are committed when used with a git URL."""
    repo_dir = _create_git_zygote_repo(tmp_path)
    data_dir = tmp_path / "changelings-data"

    extra_file = tmp_path / "extra.txt"
    extra_file.write_text("extra from clone")

    runner = CliRunner()
    runner.invoke(
        cli,
        [
            "deploy",
            str(repo_dir),
            "--add-path",
            "{}:extra.txt".format(extra_file),
            "--name",
            "clone-add-bot",
            "--provider",
            "modal",
            "--no-self-deploy",
            "--data-dir",
            str(data_dir),
        ],
    )

    changeling_dir = data_dir / "clone-add-bot"

    # Verify that the extra file is tracked in git (committed)
    ls_result = subprocess.run(
        ["git", "ls-files"],
        cwd=changeling_dir,
        capture_output=True,
        text=True,
    )
    assert "extra.txt" in ls_result.stdout

    # Verify the original changeling.toml is still there
    assert (changeling_dir / ZYGOTE_CONFIG_FILENAME).exists()


def test_deploy_agent_type_does_not_overwrite_existing_settings_toml(tmp_path: Path) -> None:
    """Verify that --agent-type does not overwrite an existing .mng/settings.toml from --add-path."""
    data_dir = tmp_path / "changelings-data"

    # Create a source .mng/settings.toml with custom content
    settings_dir = tmp_path / "mng-settings"
    settings_dir.mkdir()
    settings_file = settings_dir / "settings.toml"
    settings_file.write_text('[create_templates.custom]\nagent_type = "custom-type"\n')

    runner = CliRunner()
    runner.invoke(
        cli,
        [
            "deploy",
            "--agent-type",
            "elena-code",
            "--add-path",
            "{}:.mng/settings.toml".format(settings_file),
            "--name",
            "no-overwrite-bot",
            "--provider",
            "modal",
            "--no-self-deploy",
            "--data-dir",
            str(data_dir),
        ],
    )

    changeling_dir = data_dir / "no-overwrite-bot"
    settings_content = (changeling_dir / _MNG_SETTINGS_REL_PATH).read_text()
    # --add-path files are copied first, then _write_mng_settings_toml skips
    # creation because the file already exists. User-provided files win.
    assert "custom-type" in settings_content
