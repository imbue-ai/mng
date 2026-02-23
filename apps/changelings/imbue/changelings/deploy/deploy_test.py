# Tests for the changeling deployment logic.

import json
import subprocess
from pathlib import Path

import pytest

from imbue.changelings.conftest import make_test_changeling
from imbue.changelings.data_types import ChangelingDefinition
from imbue.changelings.data_types import DEFAULT_INITIAL_MESSAGE
from imbue.changelings.data_types import DEFAULT_SECRETS
from imbue.changelings.deploy.deploy import _forward_output
from imbue.changelings.deploy.deploy import _resolve_timezone_from_paths
from imbue.changelings.deploy.deploy import build_cron_mng_command
from imbue.changelings.deploy.deploy import build_deploy_env
from imbue.changelings.deploy.deploy import build_modal_deploy_command
from imbue.changelings.deploy.deploy import build_modal_run_command
from imbue.changelings.deploy.deploy import build_modal_secret_command
from imbue.changelings.deploy.deploy import collect_secret_values
from imbue.changelings.deploy.deploy import detect_local_timezone
from imbue.changelings.deploy.deploy import ensure_working_tree_is_clean
from imbue.changelings.deploy.deploy import find_repo_root
from imbue.changelings.deploy.deploy import get_git_config_value
from imbue.changelings.deploy.deploy import get_imbue_commit_hash
from imbue.changelings.deploy.deploy import get_imbue_repo_url
from imbue.changelings.deploy.deploy import get_modal_app_name
from imbue.changelings.deploy.deploy import get_modal_environment_name
from imbue.changelings.deploy.deploy import get_modal_secret_name
from imbue.changelings.deploy.deploy import get_modal_volume_name
from imbue.changelings.deploy.deploy import list_mng_profiles
from imbue.changelings.deploy.deploy import push_current_branch
from imbue.changelings.deploy.deploy import read_profile_user_id
from imbue.changelings.deploy.deploy import serialize_changeling_config
from imbue.changelings.errors import ChangelingDeployError
from imbue.changelings.primitives import ChangelingName

# -- get_modal_app_name tests --


def test_get_modal_app_name_prefixes_with_changeling() -> None:
    assert get_modal_app_name("code-guardian") == "changeling-code-guardian"


def test_get_modal_app_name_preserves_full_name() -> None:
    assert get_modal_app_name("my-fancy-fairy-bot") == "changeling-my-fancy-fairy-bot"


# -- get_modal_secret_name tests --


def test_get_modal_secret_name_includes_changeling_name() -> None:
    assert get_modal_secret_name("code-guardian") == "changeling-code-guardian-secrets"


def test_get_modal_secret_name_uses_secrets_suffix() -> None:
    result = get_modal_secret_name("test")
    assert result.endswith("-secrets")


# -- _forward_output tests --


def test_forward_output_writes_to_stdout(capsys: pytest.CaptureFixture[str]) -> None:
    _forward_output("hello\n", is_stdout=True)
    captured = capsys.readouterr()
    assert captured.out == "hello\n"


def test_forward_output_writes_to_stderr(capsys: pytest.CaptureFixture[str]) -> None:
    _forward_output("error\n", is_stdout=False)
    captured = capsys.readouterr()
    assert captured.err == "error\n"


# -- get_modal_volume_name tests --


def test_get_modal_volume_name_includes_changeling_name() -> None:
    assert get_modal_volume_name("code-guardian") == "changeling-code-guardian-vol"


# -- build_deploy_env tests --


def test_build_deploy_env_includes_all_required_vars() -> None:
    env = build_deploy_env(
        app_name="changeling-test",
        config_json='{"name": "test"}',
        cron_schedule="0 3 * * *",
        secret_name="changeling-test-secrets",
        imbue_repo_url="https://github.com/org/imbue.git",
        imbue_commit_hash="abc123",
        volume_name="changeling-test-vol",
        cron_timezone="America/Los_Angeles",
        git_user_name="Test User",
        git_user_email="test@example.com",
    )

    assert env["CHANGELING_MODAL_APP_NAME"] == "changeling-test"
    assert env["CHANGELING_CONFIG_JSON"] == '{"name": "test"}'
    assert env["CHANGELING_CRON_SCHEDULE"] == "0 3 * * *"
    assert env["CHANGELING_SECRET_NAME"] == "changeling-test-secrets"
    assert env["CHANGELING_IMBUE_REPO_URL"] == "https://github.com/org/imbue.git"
    assert env["CHANGELING_IMBUE_COMMIT_HASH"] == "abc123"
    assert env["CHANGELING_VOLUME_NAME"] == "changeling-test-vol"
    assert env["CHANGELING_CRON_TIMEZONE"] == "America/Los_Angeles"
    assert env["CHANGELING_GIT_USER_NAME"] == "Test User"
    assert env["CHANGELING_GIT_USER_EMAIL"] == "test@example.com"


# -- detect_local_timezone / _resolve_timezone_from_paths tests --


def test_resolve_timezone_reads_etc_timezone_when_present(tmp_path: Path) -> None:
    """When /etc/timezone exists with content, its value is returned."""
    etc_timezone = tmp_path / "timezone"
    etc_timezone.write_text("Europe/Berlin\n")
    etc_localtime = tmp_path / "localtime"

    result = _resolve_timezone_from_paths(
        etc_timezone_path=etc_timezone,
        etc_localtime_path=etc_localtime,
    )
    assert result == "Europe/Berlin"


def test_resolve_timezone_falls_back_to_localtime_symlink(tmp_path: Path) -> None:
    """When /etc/timezone is absent, the /etc/localtime symlink is used."""
    etc_timezone = tmp_path / "timezone"
    # Create a fake zoneinfo structure and symlink
    zoneinfo_dir = tmp_path / "usr" / "share" / "zoneinfo" / "America"
    zoneinfo_dir.mkdir(parents=True)
    zone_file = zoneinfo_dir / "New_York"
    zone_file.write_text("")
    etc_localtime = tmp_path / "localtime"
    etc_localtime.symlink_to(zone_file)

    result = _resolve_timezone_from_paths(
        etc_timezone_path=etc_timezone,
        etc_localtime_path=etc_localtime,
    )
    assert result == "America/New_York"


def test_resolve_timezone_returns_utc_when_no_sources(tmp_path: Path) -> None:
    """When neither /etc/timezone nor /etc/localtime exists, UTC is returned."""
    result = _resolve_timezone_from_paths(
        etc_timezone_path=tmp_path / "nonexistent_timezone",
        etc_localtime_path=tmp_path / "nonexistent_localtime",
    )
    assert result == "UTC"


def test_resolve_timezone_skips_empty_etc_timezone(tmp_path: Path) -> None:
    """When /etc/timezone exists but is empty, it falls through to the next source."""
    etc_timezone = tmp_path / "timezone"
    etc_timezone.write_text("  \n")

    result = _resolve_timezone_from_paths(
        etc_timezone_path=etc_timezone,
        etc_localtime_path=tmp_path / "nonexistent",
    )
    assert result == "UTC"


def test_detect_local_timezone_returns_nonempty_iana_string() -> None:
    """The top-level function should return a valid IANA timezone or 'UTC'."""
    result = detect_local_timezone()
    assert len(result) > 0
    assert "/" in result or result == "UTC"


# -- build_modal_deploy_command tests --


def test_build_modal_deploy_command_basic() -> None:
    cmd = build_modal_deploy_command(
        cron_runner_path=Path("/deploy/cron_runner.py"),
        environment_name=None,
    )

    assert cmd == ["uv", "run", "modal", "deploy", "/deploy/cron_runner.py"]


def test_build_modal_deploy_command_with_environment() -> None:
    cmd = build_modal_deploy_command(
        cron_runner_path=Path("/deploy/cron_runner.py"),
        environment_name="test-env",
    )

    assert cmd == ["uv", "run", "modal", "deploy", "--env", "test-env", "/deploy/cron_runner.py"]


def test_build_modal_deploy_command_environment_comes_before_path() -> None:
    """The --env flag must come before the script path (Modal CLI requirement)."""
    cmd = build_modal_deploy_command(
        cron_runner_path=Path("/script.py"),
        environment_name="my-env",
    )

    env_idx = cmd.index("--env")
    path_idx = cmd.index("/script.py")
    assert env_idx < path_idx


# -- build_modal_run_command tests --


def test_build_modal_run_command_basic() -> None:
    cmd = build_modal_run_command(
        cron_runner_path=Path("/deploy/cron_runner.py"),
        environment_name=None,
    )

    assert cmd == ["uv", "run", "modal", "run", "/deploy/cron_runner.py"]


def test_build_modal_run_command_with_environment() -> None:
    cmd = build_modal_run_command(
        cron_runner_path=Path("/deploy/cron_runner.py"),
        environment_name="test-env",
    )

    assert cmd == ["uv", "run", "modal", "run", "--env", "test-env", "/deploy/cron_runner.py"]


def test_build_modal_run_command_environment_comes_before_path() -> None:
    """The --env flag must come before the script path (Modal CLI requirement)."""
    cmd = build_modal_run_command(
        cron_runner_path=Path("/script.py"),
        environment_name="my-env",
    )

    env_idx = cmd.index("--env")
    path_idx = cmd.index("/script.py")
    assert env_idx < path_idx


# -- build_modal_secret_command tests --


def test_build_modal_secret_command_basic() -> None:
    cmd = build_modal_secret_command(
        secret_name="my-secret",
        secret_values={"KEY": "val"},
        environment_name=None,
    )

    assert cmd[:6] == ["uv", "run", "modal", "secret", "create", "my-secret"]
    assert "KEY=val" in cmd
    assert "--force" in cmd


def test_build_modal_secret_command_with_multiple_values() -> None:
    cmd = build_modal_secret_command(
        secret_name="s",
        secret_values={"A": "1", "B": "2"},
        environment_name=None,
    )

    assert "A=1" in cmd
    assert "B=2" in cmd


def test_build_modal_secret_command_with_environment() -> None:
    cmd = build_modal_secret_command(
        secret_name="s",
        secret_values={"A": "1"},
        environment_name="test-env",
    )

    assert "--env" in cmd
    assert "test-env" in cmd


def test_build_modal_secret_command_force_flag_always_present() -> None:
    """The --force flag ensures the secret is updated if it already exists."""
    cmd = build_modal_secret_command(
        secret_name="s",
        secret_values={},
        environment_name=None,
    )

    assert "--force" in cmd


def test_build_modal_secret_command_empty_values() -> None:
    """An empty secret_values dict should still produce a valid command."""
    cmd = build_modal_secret_command(
        secret_name="empty-secret",
        secret_values={},
        environment_name=None,
    )

    assert "empty-secret" in cmd
    assert "--force" in cmd


# -- collect_secret_values tests --


def test_collect_secret_values_returns_matching_values() -> None:
    env = {"TOKEN": "abc", "KEY": "xyz", "OTHER": "ignored"}
    result = collect_secret_values(["TOKEN", "KEY"], env)

    assert result == {"TOKEN": "abc", "KEY": "xyz"}


def test_collect_secret_values_skips_missing() -> None:
    env = {"TOKEN": "abc"}
    result = collect_secret_values(["TOKEN", "MISSING_KEY"], env)

    assert result == {"TOKEN": "abc"}


def test_collect_secret_values_returns_empty_when_none_found() -> None:
    env = {"UNRELATED": "value"}
    result = collect_secret_values(["TOKEN", "KEY"], env)

    assert result == {}


def test_collect_secret_values_empty_names() -> None:
    env = {"TOKEN": "abc"}
    result = collect_secret_values([], env)

    assert result == {}


# -- serialize_changeling_config tests --


def test_serialize_changeling_config_produces_valid_json() -> None:
    changeling = ChangelingDefinition(
        name=ChangelingName("test"),
        agent_type="code-guardian",
    )

    config_json = serialize_changeling_config(changeling)
    parsed = json.loads(config_json)

    assert parsed["name"] == "test"
    assert parsed["agent_type"] == "code-guardian"


def test_serialize_changeling_config_includes_all_fields() -> None:
    changeling = ChangelingDefinition(
        name=ChangelingName("my-fairy"),
        agent_type="claude",
        branch="develop",
        initial_message="Fix all the things",
        extra_mng_args="--verbose",
        env_vars={"DEBUG": "true"},
        mng_options={"gpu": "a10g"},
        secrets=("MY_TOKEN",),
    )

    config_json = serialize_changeling_config(changeling)
    parsed = json.loads(config_json)

    assert parsed["name"] == "my-fairy"
    assert parsed["agent_type"] == "claude"
    assert parsed["branch"] == "develop"
    assert parsed["initial_message"] == "Fix all the things"
    assert parsed["extra_mng_args"] == "--verbose"
    assert parsed["env_vars"] == {"DEBUG": "true"}
    assert parsed["mng_options"] == {"gpu": "a10g"}
    assert parsed["secrets"] == ["MY_TOKEN"]


def test_serialize_changeling_config_roundtrip_preserves_defaults() -> None:
    """Serialized config should include default values for completeness."""
    changeling = ChangelingDefinition(
        name=ChangelingName("test"),
    )

    config_json = serialize_changeling_config(changeling)
    parsed = json.loads(config_json)

    assert parsed["branch"] == "main"
    assert parsed["initial_message"] == DEFAULT_INITIAL_MESSAGE
    assert parsed["secrets"] == list(DEFAULT_SECRETS)
    assert parsed["is_enabled"] is True


# -- build_cron_mng_command tests --


def test_build_cron_mng_command_starts_with_uv_run_mng() -> None:
    """The cron command should use `uv run mng` instead of python -m."""
    changeling = make_test_changeling()
    env_file = Path("/tmp/test.env")
    cmd = build_cron_mng_command(changeling, env_file)

    assert cmd[0] == "uv"
    assert cmd[1] == "run"
    assert cmd[2] == "mng"
    assert cmd[3] == "create"


def test_build_cron_mng_command_does_not_include_python_module_invocation() -> None:
    """The cron command should use uv run mng, not python -m."""
    changeling = make_test_changeling()
    env_file = Path("/tmp/test.env")
    cmd = build_cron_mng_command(changeling, env_file)

    assert "-m" not in cmd
    assert "imbue.mng.main" not in cmd


def test_build_cron_mng_command_includes_modal_flag() -> None:
    """The cron command should always target Modal."""
    changeling = make_test_changeling()
    env_file = Path("/tmp/test.env")
    cmd = build_cron_mng_command(changeling, env_file)

    in_idx = cmd.index("--in")
    assert cmd[in_idx + 1] == "modal"


def test_build_cron_mng_command_includes_env_file() -> None:
    """The cron command should include the env file path."""
    changeling = make_test_changeling()
    env_file = Path("/tmp/my-secrets.env")
    cmd = build_cron_mng_command(changeling, env_file)

    file_idx = cmd.index("--host-env-file")
    assert cmd[file_idx + 1] == "/tmp/my-secrets.env"


def test_build_cron_mng_command_includes_core_flags() -> None:
    """The cron command should include all core changeling flags."""
    changeling = make_test_changeling()
    env_file = Path("/tmp/test.env")
    cmd = build_cron_mng_command(changeling, env_file)

    assert "--no-connect" in cmd
    assert "--no-ensure-clean" in cmd
    assert "CREATOR=changeling" in cmd


def test_build_cron_mng_command_includes_agent_name_with_timestamp() -> None:
    """The agent name should include the changeling name and a timestamp."""
    changeling = make_test_changeling(name="my-guardian")
    env_file = Path("/tmp/test.env")
    cmd = build_cron_mng_command(changeling, env_file)

    agent_name = cmd[4]
    assert agent_name.startswith("my-guardian-")


def test_build_cron_mng_command_uses_agent_type() -> None:
    """The cron command should use the configured agent type."""
    changeling = make_test_changeling(agent_type="code-guardian")
    env_file = Path("/tmp/test.env")
    cmd = build_cron_mng_command(changeling, env_file)

    assert cmd[5] == "code-guardian"


def test_build_cron_mng_command_includes_verbose_flag() -> None:
    """The mng create command should include -vv for verbose output."""
    changeling = make_test_changeling()
    env_file = Path("/tmp/test.env")
    cmd = build_cron_mng_command(changeling, env_file)

    assert "-vv" in cmd


def test_build_cron_mng_command_includes_extra_mng_args() -> None:
    """Extra mng args should be appended to the cron command."""
    changeling = make_test_changeling(extra_mng_args="--verbose --timeout 300")
    env_file = Path("/tmp/test.env")
    cmd = build_cron_mng_command(changeling, env_file)

    assert "--verbose" in cmd
    assert "--timeout" in cmd
    assert "300" in cmd


def test_build_cron_mng_command_includes_dangerously_skip_permissions() -> None:
    """The cron command should pass --dangerously-skip-permissions after -- to the agent."""
    changeling = make_test_changeling()
    env_file = Path("/tmp/test.env")
    cmd = build_cron_mng_command(changeling, env_file)

    assert "--" in cmd
    separator_idx = cmd.index("--")
    assert "--dangerously-skip-permissions" in cmd[separator_idx:]


# -- find_repo_root tests (using real git) --


def test_find_repo_root_returns_path_in_git_repo(imbue_repo_cwd: Path) -> None:
    """When called from inside a git repo, find_repo_root should return a valid path."""
    result = find_repo_root()

    assert result.is_dir()
    assert (result / ".git").exists()


def test_find_repo_root_raises_outside_git_repo() -> None:
    """When called from outside a git repo, ChangelingDeployError should be raised."""
    with pytest.raises(ChangelingDeployError, match="Could not find git repository root"):
        find_repo_root()


# -- get_imbue_commit_hash tests --


def test_get_imbue_commit_hash_returns_hex_string(imbue_repo_cwd: Path) -> None:
    """The commit hash should be a 40-character hex string."""
    result = get_imbue_commit_hash()

    assert len(result) == 40
    assert all(c in "0123456789abcdef" for c in result)


def test_get_imbue_commit_hash_raises_outside_git_repo() -> None:
    with pytest.raises(ChangelingDeployError, match="Could not get current commit hash"):
        get_imbue_commit_hash()


# -- get_imbue_repo_url tests --


def test_get_imbue_repo_url_returns_non_empty_string(imbue_repo_cwd: Path) -> None:
    """The imbue repo URL should be a non-empty string."""
    result = get_imbue_repo_url()

    assert len(result) > 0


def test_get_imbue_repo_url_returns_https_url(imbue_repo_cwd: Path) -> None:
    """The imbue repo URL should be HTTPS (SSH URLs are converted)."""
    result = get_imbue_repo_url()

    assert result.startswith("https://")


def test_get_imbue_repo_url_raises_outside_git_repo() -> None:
    with pytest.raises(ChangelingDeployError, match="Could not get repository clone URL"):
        get_imbue_repo_url()


# -- list_mng_profiles tests --


def test_list_mng_profiles_returns_empty_when_no_profiles_dir() -> None:
    result = list_mng_profiles()
    assert result == []


def test_list_mng_profiles_returns_profile_ids(tmp_path: Path) -> None:
    profiles_dir = tmp_path / ".mng" / "profiles"
    (profiles_dir / "abc123").mkdir(parents=True)
    (profiles_dir / "def456").mkdir(parents=True)

    result = list_mng_profiles()

    assert result == ["abc123", "def456"]


def test_list_mng_profiles_ignores_files(tmp_path: Path) -> None:
    """Only directories should be listed as profiles."""
    profiles_dir = tmp_path / ".mng" / "profiles"
    profiles_dir.mkdir(parents=True)
    (profiles_dir / "real-profile").mkdir()
    (profiles_dir / "not-a-profile.txt").write_text("ignored")

    result = list_mng_profiles()

    assert result == ["real-profile"]


# -- read_profile_user_id tests --


def test_read_profile_user_id_returns_user_id(tmp_path: Path) -> None:
    profile_dir = tmp_path / ".mng" / "profiles" / "my-profile"
    profile_dir.mkdir(parents=True)
    (profile_dir / "user_id").write_text("abc123def456\n")

    result = read_profile_user_id("my-profile")

    assert result == "abc123def456"


def test_read_profile_user_id_raises_when_file_missing() -> None:
    with pytest.raises(ChangelingDeployError, match="user_id file not found"):
        read_profile_user_id("nonexistent-profile")


# -- get_modal_environment_name tests --


def test_get_modal_environment_name_formats_correctly() -> None:
    assert get_modal_environment_name("abc123") == "mng-abc123"


def test_get_modal_environment_name_uses_full_user_id() -> None:
    result = get_modal_environment_name("8caed3bc40df435fae5817ea0afdbf77")
    assert result == "mng-8caed3bc40df435fae5817ea0afdbf77"


# -- get_git_config_value tests --


def test_get_git_config_value_returns_none_when_not_set() -> None:
    """With an isolated home dir (no gitconfig), all keys should return None."""
    result = get_git_config_value("user.name")
    assert result is None


def test_get_git_config_value_returns_value_when_set(tmp_path: Path) -> None:
    """When a global gitconfig exists with the key, return its value."""
    gitconfig = tmp_path / ".gitconfig"
    gitconfig.write_text("[user]\n\tname = Test Changeling\n\temail = test@example.com\n")

    assert get_git_config_value("user.name") == "Test Changeling"
    assert get_git_config_value("user.email") == "test@example.com"


# -- ensure_working_tree_is_clean tests --


def _init_git_repo(repo_dir: Path) -> None:
    """Initialize a git repo with local user config and an initial commit."""
    subprocess.run(["git", "init"], cwd=repo_dir, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=repo_dir, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo_dir, check=True, capture_output=True)
    (repo_dir / "initial.txt").write_text("initial")
    subprocess.run(["git", "add", "."], cwd=repo_dir, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=repo_dir, check=True, capture_output=True)


def test_ensure_working_tree_is_clean_succeeds_in_clean_repo(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When the working tree is clean, no error is raised."""
    repo_dir = tmp_path / "clean-repo"
    repo_dir.mkdir()
    _init_git_repo(repo_dir)

    monkeypatch.chdir(repo_dir)
    ensure_working_tree_is_clean()


def test_ensure_working_tree_is_clean_raises_with_untracked_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When the working tree has an untracked file, ChangelingDeployError is raised."""
    repo_dir = tmp_path / "dirty-repo"
    repo_dir.mkdir()
    _init_git_repo(repo_dir)
    (repo_dir / "untracked.txt").write_text("untracked")

    monkeypatch.chdir(repo_dir)
    with pytest.raises(ChangelingDeployError, match="uncommitted changes"):
        ensure_working_tree_is_clean()


def test_ensure_working_tree_is_clean_raises_with_staged_changes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When the working tree has staged but uncommitted changes, ChangelingDeployError is raised."""
    repo_dir = tmp_path / "staged-repo"
    repo_dir.mkdir()
    _init_git_repo(repo_dir)
    (repo_dir / "staged.txt").write_text("staged")
    subprocess.run(["git", "add", "staged.txt"], cwd=repo_dir, check=True, capture_output=True)

    monkeypatch.chdir(repo_dir)
    with pytest.raises(ChangelingDeployError, match="uncommitted changes"):
        ensure_working_tree_is_clean()


def test_ensure_working_tree_is_clean_raises_outside_git_repo(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When not inside a git repo, ChangelingDeployError is raised."""
    non_repo_dir = tmp_path / "not-a-repo"
    non_repo_dir.mkdir()
    monkeypatch.chdir(non_repo_dir)

    with pytest.raises(ChangelingDeployError, match="Could not check git status"):
        ensure_working_tree_is_clean()


# -- push_current_branch tests --


def _init_git_repo_with_remote(tmp_path: Path) -> Path:
    """Create a bare remote repo, clone it, make an initial commit, and push.

    Returns the path to the working repo (already pushed to the bare remote).
    """
    bare_repo = tmp_path / "bare.git"
    bare_repo.mkdir()
    subprocess.run(["git", "init", "--bare"], cwd=bare_repo, check=True, capture_output=True)

    work_repo = tmp_path / "work"
    subprocess.run(["git", "clone", str(bare_repo), str(work_repo)], check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=work_repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=work_repo, check=True, capture_output=True)
    (work_repo / "file.txt").write_text("content")
    subprocess.run(["git", "add", "."], cwd=work_repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=work_repo, check=True, capture_output=True)
    subprocess.run(["git", "push"], cwd=work_repo, check=True, capture_output=True)
    return work_repo


def test_push_current_branch_succeeds_when_nothing_to_push(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When the current branch is up to date with remote, push succeeds."""
    work_repo = _init_git_repo_with_remote(tmp_path)

    monkeypatch.chdir(work_repo)
    push_current_branch()


def test_push_current_branch_pushes_unpushed_commits(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When there are unpushed commits, push succeeds and pushes them."""
    work_repo = _init_git_repo_with_remote(tmp_path)

    # Make another commit without pushing
    (work_repo / "new.txt").write_text("new content")
    subprocess.run(["git", "add", "."], cwd=work_repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "new commit"], cwd=work_repo, check=True, capture_output=True)

    monkeypatch.chdir(work_repo)
    push_current_branch()


def test_push_current_branch_raises_when_no_remote(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When there is no remote configured, push fails and ChangelingDeployError is raised."""
    repo_dir = tmp_path / "no-remote-repo"
    repo_dir.mkdir()
    _init_git_repo(repo_dir)

    monkeypatch.chdir(repo_dir)
    with pytest.raises(ChangelingDeployError, match="Failed to push"):
        push_current_branch()
