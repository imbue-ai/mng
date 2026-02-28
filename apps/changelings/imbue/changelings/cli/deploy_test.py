import subprocess
from pathlib import Path

from click.testing import CliRunner
from click.testing import Result

from imbue.changelings.cli.deploy import _MNG_SETTINGS_REL_PATH
from imbue.changelings.main import cli
from imbue.changelings.testing import init_and_commit_git_repo

_RUNNER = CliRunner()


def _create_git_repo_with_settings(tmp_path: Path, agent_type: str = "elena-code") -> Path:
    """Create a minimal git repo with .mng/settings.toml for testing."""
    repo_dir = tmp_path / "my-agent-repo"
    repo_dir.mkdir()
    settings_dir = repo_dir / ".mng"
    settings_dir.mkdir()
    (settings_dir / "settings.toml").write_text(
        '[create_templates.entrypoint]\nagent_type = "{}"\n'.format(agent_type)
    )
    init_and_commit_git_repo(repo_dir, tmp_path)
    return repo_dir


def _data_dir_args(tmp_path: Path) -> list[str]:
    """Return the --data-dir CLI args pointing to a temp directory."""
    return ["--data-dir", str(tmp_path / "changelings-data")]


def _deploy_with_agent_type(
    tmp_path: Path,
    agent_type: str = "elena-code",
    name: str | None = "test-bot",
    add_paths: list[str] | None = None,
    provider: str = "modal",
    input_text: str | None = None,
) -> Result:
    """Invoke changeling deploy with --agent-type and standard non-interactive flags.

    Uses --provider modal by default to abort before mng create (since mng create
    requires a running mng environment). Set name=None to test the name prompt.
    """
    args: list[str] = ["deploy", "--agent-type", agent_type]

    if name is not None:
        args.extend(["--name", name])

    for ap in add_paths or []:
        args.extend(["--add-path", ap])

    args.extend(["--provider", provider, "--no-self-deploy"])
    args.extend(_data_dir_args(tmp_path))

    return _RUNNER.invoke(cli, args, input=input_text)


def _deploy_with_git_url(
    tmp_path: Path,
    git_url: str,
    name: str | None = "test-bot",
    add_paths: list[str] | None = None,
    provider: str = "modal",
    input_text: str | None = None,
    agent_type: str | None = None,
) -> Result:
    """Invoke changeling deploy with a git URL and standard non-interactive flags."""
    args: list[str] = ["deploy", git_url]

    if agent_type is not None:
        args.extend(["--agent-type", agent_type])

    if name is not None:
        args.extend(["--name", name])

    for ap in add_paths or []:
        args.extend(["--add-path", ap])

    args.extend(["--provider", provider, "--no-self-deploy"])
    args.extend(_data_dir_args(tmp_path))

    return _RUNNER.invoke(cli, args, input=input_text)


def _changeling_dir(tmp_path: Path, name: str) -> Path:
    """Return the expected changeling directory for a given name."""
    return tmp_path / "changelings-data" / name


# --- Tests for git URL deployment ---


def test_deploy_fails_for_invalid_git_url(tmp_path: Path) -> None:
    result = _RUNNER.invoke(cli, ["deploy", "/nonexistent/repo/path", *_data_dir_args(tmp_path)])

    assert result.exit_code != 0
    assert "git clone failed" in result.output


def test_deploy_fails_when_no_settings_toml(tmp_path: Path) -> None:
    """Cloning a repo without .mng/settings.toml should fail."""
    repo_dir = tmp_path / "empty-repo"
    repo_dir.mkdir()
    init_and_commit_git_repo(repo_dir, tmp_path, allow_empty=True)

    result = _RUNNER.invoke(cli, ["deploy", str(repo_dir), *_data_dir_args(tmp_path)])

    assert result.exit_code != 0
    assert ".mng/settings.toml" in result.output


def test_deploy_cleans_up_temp_dir_on_clone_failure(tmp_path: Path) -> None:
    """Verify that a failed clone does not leave temporary directories behind."""
    data_dir = tmp_path / "changelings-data"

    _RUNNER.invoke(cli, ["deploy", "/nonexistent/repo/path", "--data-dir", str(data_dir)])

    if data_dir.exists():
        leftover = [p for p in data_dir.iterdir() if p.name.startswith(".tmp-")]
        assert leftover == []


def test_deploy_cleans_up_temp_dir_on_missing_settings(tmp_path: Path) -> None:
    """Verify that a missing .mng/settings.toml does not leave temporary directories behind."""
    repo_dir = tmp_path / "empty-repo"
    repo_dir.mkdir()
    init_and_commit_git_repo(repo_dir, tmp_path, allow_empty=True)
    data_dir = tmp_path / "changelings-data"

    _RUNNER.invoke(cli, ["deploy", str(repo_dir), "--data-dir", str(data_dir)])

    leftover = [p for p in data_dir.iterdir() if p.name.startswith(".tmp-")]
    assert leftover == []


def test_deploy_stores_clone_under_agent_name(tmp_path: Path) -> None:
    """Verify that the clone is stored at <data-dir>/<agent-name>/."""
    repo_dir = _create_git_repo_with_settings(tmp_path)

    result = _deploy_with_git_url(tmp_path, str(repo_dir), name="my-bot")

    assert result.exit_code != 0
    assert "Only local deployment is supported" in result.output

    cdir = _changeling_dir(tmp_path, "my-bot")
    assert cdir.is_dir()
    assert (cdir / _MNG_SETTINGS_REL_PATH).exists()


def test_deploy_rejects_modal_provider(tmp_path: Path) -> None:
    repo_dir = _create_git_repo_with_settings(tmp_path)

    result = _RUNNER.invoke(
        cli,
        ["deploy", str(repo_dir), *_data_dir_args(tmp_path)],
        input="test-bot\n2\nN\n",
    )

    assert result.exit_code != 0
    assert "Only local deployment is supported" in result.output


def test_deploy_rejects_docker_provider(tmp_path: Path) -> None:
    repo_dir = _create_git_repo_with_settings(tmp_path)

    result = _RUNNER.invoke(
        cli,
        ["deploy", str(repo_dir), *_data_dir_args(tmp_path)],
        input="test-bot\n3\nN\n",
    )

    assert result.exit_code != 0
    assert "Only local deployment is supported" in result.output


def test_deploy_shows_prompts(tmp_path: Path) -> None:
    """Verify all three prompts appear when deploying (using modal to abort before mng create)."""
    repo_dir = _create_git_repo_with_settings(tmp_path)

    result = _RUNNER.invoke(
        cli,
        ["deploy", str(repo_dir), *_data_dir_args(tmp_path)],
        input="my-agent\n2\nN\n",
    )

    assert "What would you like to name this agent" in result.output
    assert "Where do you want to run" in result.output
    assert "launch its own agents" in result.output


def test_deploy_displays_clone_url(tmp_path: Path) -> None:
    repo_dir = _create_git_repo_with_settings(tmp_path)

    result = _RUNNER.invoke(
        cli,
        ["deploy", str(repo_dir), *_data_dir_args(tmp_path)],
        input="test-bot\n2\nN\n",
    )

    assert "Cloning repository" in result.output


def test_deploy_name_flag_skips_prompt(tmp_path: Path) -> None:
    """Verify that --name skips the name prompt."""
    repo_dir = _create_git_repo_with_settings(tmp_path)

    result = _deploy_with_git_url(tmp_path, str(repo_dir), name="my-custom-name")

    assert "What would you like to name this agent" not in result.output
    assert result.exit_code != 0
    assert "Only local deployment is supported" in result.output


def test_deploy_provider_flag_skips_prompt(tmp_path: Path) -> None:
    """Verify that --provider skips the provider prompt."""
    repo_dir = _create_git_repo_with_settings(tmp_path)

    result = _RUNNER.invoke(
        cli,
        ["deploy", str(repo_dir), "--provider", "modal", "--no-self-deploy", *_data_dir_args(tmp_path)],
        input="test-bot\n",
    )

    assert "Where do you want to run" not in result.output
    assert result.exit_code != 0
    assert "Only local deployment is supported" in result.output


def test_deploy_self_deploy_flag_skips_prompt(tmp_path: Path) -> None:
    """Verify that --no-self-deploy skips the self-deploy prompt."""
    repo_dir = _create_git_repo_with_settings(tmp_path)

    result = _RUNNER.invoke(
        cli,
        ["deploy", str(repo_dir), "--no-self-deploy", "--provider", "modal", *_data_dir_args(tmp_path)],
        input="test-bot\n",
    )

    assert "launch its own agents" not in result.output


def test_deploy_all_flags_skip_all_prompts(tmp_path: Path) -> None:
    """Verify that providing all flags skips all interactive prompts."""
    repo_dir = _create_git_repo_with_settings(tmp_path)

    result = _deploy_with_git_url(tmp_path, str(repo_dir), name="bot")

    assert "What would you like to name this agent" not in result.output
    assert "Where do you want to run" not in result.output
    assert "launch its own agents" not in result.output
    assert result.exit_code != 0
    assert "Only local deployment is supported" in result.output


def test_deploy_rejects_duplicate_changeling_name(tmp_path: Path) -> None:
    """Verify that deploying with a name that already has a directory fails."""
    repo_dir = _create_git_repo_with_settings(tmp_path)

    result1 = _deploy_with_git_url(tmp_path, str(repo_dir), name="dup-bot")
    assert result1.exit_code != 0

    result2 = _deploy_with_git_url(tmp_path, str(repo_dir), name="dup-bot")
    assert result2.exit_code != 0
    assert "already exists" in result2.output


# --- Tests for --agent-type (no git URL) ---


def test_deploy_agent_type_creates_mng_settings_toml(tmp_path: Path) -> None:
    """Verify that --agent-type creates .mng/settings.toml with the correct template."""
    result = _deploy_with_agent_type(tmp_path, name="my-elena")

    assert result.exit_code != 0
    assert "Only local deployment is supported" in result.output

    settings_path = _changeling_dir(tmp_path, "my-elena") / _MNG_SETTINGS_REL_PATH
    assert settings_path.exists()

    settings_content = settings_path.read_text()
    assert "[create_templates.entrypoint]" in settings_content
    assert 'agent_type = "elena-code"' in settings_content


def test_deploy_agent_type_creates_git_repo_with_commit(tmp_path: Path) -> None:
    """Verify that --agent-type creates a git repo with an initial commit."""
    _deploy_with_agent_type(tmp_path, name="my-elena")

    cdir = _changeling_dir(tmp_path, "my-elena")
    assert (cdir / ".git").is_dir()

    log_result = subprocess.run(
        ["git", "log", "--oneline"],
        cwd=cdir,
        capture_output=True,
        text=True,
    )
    assert log_result.returncode == 0
    assert "Initial changeling setup" in log_result.stdout


def test_deploy_agent_type_defaults_name_to_agent_type(tmp_path: Path) -> None:
    """Verify that --agent-type defaults the agent name prompt to the agent type value."""
    result = _deploy_with_agent_type(tmp_path, name=None, input_text="elena-code\n")

    assert "elena-code" in result.output
    assert _changeling_dir(tmp_path, "elena-code").is_dir()


def test_deploy_fails_without_git_url_or_agent_type(tmp_path: Path) -> None:
    """Verify that deploy fails when neither GIT_URL nor --agent-type is provided."""
    result = _RUNNER.invoke(cli, ["deploy", *_data_dir_args(tmp_path)])

    assert result.exit_code != 0
    assert "Either GIT_URL or --agent-type must be provided" in result.output


def test_deploy_agent_type_shows_creating_message(tmp_path: Path) -> None:
    """Verify that --agent-type shows a 'Creating changeling repo' message instead of 'Cloning'."""
    result = _deploy_with_agent_type(tmp_path)

    assert "Cloning repository" not in result.output
    assert "Deploying changeling from" in result.output


# --- Tests for --add-path ---


def test_deploy_add_path_copies_file_into_repo(tmp_path: Path) -> None:
    """Verify that --add-path copies a file into the cloned repo."""
    repo_dir = _create_git_repo_with_settings(tmp_path)

    extra_file = tmp_path / "extra.txt"
    extra_file.write_text("extra content")

    result = _deploy_with_git_url(
        tmp_path,
        str(repo_dir),
        name="add-path-bot",
        add_paths=["{}:extra.txt".format(extra_file)],
    )

    assert result.exit_code != 0
    assert "Only local deployment is supported" in result.output
    assert (_changeling_dir(tmp_path, "add-path-bot") / "extra.txt").read_text() == "extra content"


def test_deploy_add_path_copies_directory_into_repo(tmp_path: Path) -> None:
    """Verify that --add-path recursively copies a directory into the repo."""
    repo_dir = _create_git_repo_with_settings(tmp_path)

    src_dir = tmp_path / "src-config"
    src_dir.mkdir()
    (src_dir / "a.txt").write_text("file a")
    sub = src_dir / "sub"
    sub.mkdir()
    (sub / "b.txt").write_text("file b")

    result = _deploy_with_git_url(
        tmp_path,
        str(repo_dir),
        name="dir-bot",
        add_paths=["{}:config".format(src_dir)],
    )

    assert result.exit_code != 0
    cdir = _changeling_dir(tmp_path, "dir-bot")
    assert (cdir / "config" / "a.txt").read_text() == "file a"
    assert (cdir / "config" / "sub" / "b.txt").read_text() == "file b"


def test_deploy_add_path_with_agent_type(tmp_path: Path) -> None:
    """Verify that --add-path works with --agent-type (no git URL)."""
    extra_file = tmp_path / "my-config.json"
    extra_file.write_text('{"key": "value"}')

    result = _deploy_with_agent_type(
        tmp_path,
        name="path-elena",
        add_paths=["{}:config/my-config.json".format(extra_file)],
    )

    assert result.exit_code != 0
    assert "Only local deployment is supported" in result.output

    cdir = _changeling_dir(tmp_path, "path-elena")
    assert (cdir / "config" / "my-config.json").read_text() == '{"key": "value"}'
    assert (cdir / _MNG_SETTINGS_REL_PATH).exists()


def test_deploy_add_path_multiple_paths(tmp_path: Path) -> None:
    """Verify that multiple --add-path args are all copied."""
    file_a = tmp_path / "a.txt"
    file_a.write_text("aaa")
    file_b = tmp_path / "b.txt"
    file_b.write_text("bbb")

    result = _deploy_with_agent_type(
        tmp_path,
        name="multi-bot",
        add_paths=["{}:a.txt".format(file_a), "{}:b.txt".format(file_b)],
    )

    assert result.exit_code != 0
    cdir = _changeling_dir(tmp_path, "multi-bot")
    assert (cdir / "a.txt").read_text() == "aaa"
    assert (cdir / "b.txt").read_text() == "bbb"


def test_deploy_add_path_fails_for_nonexistent_source(tmp_path: Path) -> None:
    """Verify that --add-path fails when the source path does not exist."""
    result = _deploy_with_agent_type(
        tmp_path,
        name="bad-bot",
        add_paths=["/nonexistent/path:dest.txt"],
    )

    assert result.exit_code != 0
    assert "does not exist" in result.output


def test_deploy_add_path_fails_for_invalid_format(tmp_path: Path) -> None:
    """Verify that --add-path fails when the format is not SRC:DEST."""
    result = _deploy_with_agent_type(
        tmp_path,
        name="bad-bot",
        add_paths=["no-colon-here"],
    )

    assert result.exit_code != 0
    assert "SRC:DEST" in result.output


def test_deploy_add_path_fails_for_absolute_dest(tmp_path: Path) -> None:
    """Verify that --add-path fails when DEST is an absolute path."""
    extra_file = tmp_path / "file.txt"
    extra_file.write_text("content")

    result = _deploy_with_agent_type(
        tmp_path,
        name="bad-bot",
        add_paths=["{}:/absolute/dest.txt".format(extra_file)],
    )

    assert result.exit_code != 0
    assert "must be relative" in result.output


def test_deploy_add_path_files_are_committed(tmp_path: Path) -> None:
    """Verify that --add-path files are included in the git commit."""
    extra_file = tmp_path / "extra.txt"
    extra_file.write_text("committed content")

    _deploy_with_agent_type(
        tmp_path,
        name="commit-bot",
        add_paths=["{}:extra.txt".format(extra_file)],
    )

    ls_result = subprocess.run(
        ["git", "ls-files"],
        cwd=_changeling_dir(tmp_path, "commit-bot"),
        capture_output=True,
        text=True,
    )
    assert "extra.txt" in ls_result.stdout


def test_deploy_add_path_with_clone_commits_added_files(tmp_path: Path) -> None:
    """Verify that --add-path files are committed when used with a git URL."""
    repo_dir = _create_git_repo_with_settings(tmp_path)

    extra_file = tmp_path / "extra.txt"
    extra_file.write_text("extra from clone")

    _deploy_with_git_url(
        tmp_path,
        str(repo_dir),
        name="clone-add-bot",
        add_paths=["{}:extra.txt".format(extra_file)],
    )

    cdir = _changeling_dir(tmp_path, "clone-add-bot")

    ls_result = subprocess.run(
        ["git", "ls-files"],
        cwd=cdir,
        capture_output=True,
        text=True,
    )
    assert "extra.txt" in ls_result.stdout
    assert (cdir / _MNG_SETTINGS_REL_PATH).exists()


def test_deploy_agent_type_does_not_overwrite_existing_settings_toml(tmp_path: Path) -> None:
    """Verify that --agent-type does not overwrite an existing .mng/settings.toml from --add-path."""
    settings_dir = tmp_path / "mng-settings"
    settings_dir.mkdir()
    settings_file = settings_dir / "settings.toml"
    settings_file.write_text('[create_templates.custom]\nagent_type = "custom-type"\n')

    _deploy_with_agent_type(
        tmp_path,
        name="no-overwrite-bot",
        add_paths=["{}:.mng/settings.toml".format(settings_file)],
    )

    settings_content = (_changeling_dir(tmp_path, "no-overwrite-bot") / _MNG_SETTINGS_REL_PATH).read_text()
    # --add-path files are copied first, then _write_mng_settings_toml skips
    # creation because the file already exists. User-provided files win.
    assert "custom-type" in settings_content
