import pluggy
from click.testing import CliRunner

from imbue.mngr.cli.limit import LimitCliOptions
from imbue.mngr.cli.limit import _build_updated_activity_config
from imbue.mngr.cli.limit import _build_updated_permissions
from imbue.mngr.cli.limit import limit
from imbue.mngr.interfaces.data_types import ActivityConfig
from imbue.mngr.primitives import ActivitySource
from imbue.mngr.primitives import IdleMode
from imbue.mngr.primitives import Permission


def test_limit_cli_options_fields() -> None:
    """Test LimitCliOptions has required fields."""
    opts = LimitCliOptions(
        agents=("agent1", "agent2"),
        agent_list=("agent3",),
        hosts=(),
        limit_all=False,
        dry_run=True,
        include=(),
        exclude=(),
        stdin=False,
        start_on_boot=None,
        idle_timeout=None,
        idle_mode=None,
        activity_sources=None,
        add_activity_source=(),
        remove_activity_source=(),
        grant=(),
        revoke=(),
        refresh_ssh_keys=False,
        add_ssh_key=(),
        remove_ssh_key=(),
        output_format="human",
        quiet=False,
        verbose=0,
        log_file=None,
        log_commands=None,
        log_command_output=None,
        log_env_vars=None,
        project_context_path=None,
        plugin=(),
        disable_plugin=(),
    )
    assert opts.agents == ("agent1", "agent2")
    assert opts.agent_list == ("agent3",)
    assert opts.limit_all is False
    assert opts.dry_run is True
    assert opts.hosts == ()


def test_limit_requires_target(
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test that limit requires at least one agent, host, or --all."""
    result = cli_runner.invoke(
        limit,
        ["--idle-timeout", "300"],
        obj=plugin_manager,
        catch_exceptions=True,
    )

    assert result.exit_code != 0
    assert "Must specify at least one agent, --host, or --all" in result.output


def test_limit_requires_setting(
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test that limit requires at least one setting to change."""
    result = cli_runner.invoke(
        limit,
        ["my-agent"],
        obj=plugin_manager,
        catch_exceptions=True,
    )

    assert result.exit_code != 0
    assert "Must specify at least one setting to change" in result.output


def test_limit_cannot_combine_agents_and_all(
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test that --all cannot be combined with agent names."""
    result = cli_runner.invoke(
        limit,
        ["my-agent", "--all", "--idle-timeout", "300"],
        obj=plugin_manager,
        catch_exceptions=True,
    )

    assert result.exit_code != 0
    assert "Cannot specify both agent names and --all" in result.output


def test_limit_future_options_raise_not_implemented(
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test that [future] options raise NotImplementedError."""
    future_option_sets = [
        ["--all", "--idle-timeout", "300", "--include", "some-filter"],
        ["--all", "--idle-timeout", "300", "--exclude", "some-filter"],
        ["--all", "--idle-timeout", "300", "--stdin"],
        ["--all", "--idle-timeout", "300", "--refresh-ssh-keys"],
        ["--all", "--idle-timeout", "300", "--add-ssh-key", "key.pub"],
        ["--all", "--idle-timeout", "300", "--remove-ssh-key", "key.pub"],
    ]
    for args in future_option_sets:
        result = cli_runner.invoke(
            limit,
            args,
            obj=plugin_manager,
            catch_exceptions=True,
        )
        assert result.exit_code != 0, f"Expected failure for args {args}, got exit_code=0"


def test_limit_all_with_no_agents(
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test --all when no agents exist (should succeed with 'no agents found')."""
    result = cli_runner.invoke(
        limit,
        ["--all", "--idle-timeout", "300"],
        obj=plugin_manager,
        catch_exceptions=False,
    )

    assert result.exit_code == 0
    assert "No agents found to configure" in result.output


def test_limit_host_only_rejects_agent_settings(
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test that agent-level settings are rejected when only --host is specified."""
    result = cli_runner.invoke(
        limit,
        ["--host", "some-host", "--start-on-boot"],
        obj=plugin_manager,
        catch_exceptions=True,
    )

    assert result.exit_code != 0
    assert "Agent-level settings" in result.output


def test_build_updated_permissions_grant() -> None:
    """Test that grant adds permissions."""
    current = [Permission("read")]
    result = _build_updated_permissions(
        current=current,
        grant=("write", "execute"),
        revoke=(),
    )
    result_strs = [str(p) for p in result]
    assert "read" in result_strs
    assert "write" in result_strs
    assert "execute" in result_strs


def test_build_updated_permissions_revoke() -> None:
    """Test that revoke removes permissions."""
    current = [Permission("read"), Permission("write"), Permission("execute")]
    result = _build_updated_permissions(
        current=current,
        grant=(),
        revoke=("write",),
    )
    result_strs = [str(p) for p in result]
    assert "read" in result_strs
    assert "write" not in result_strs
    assert "execute" in result_strs


def test_build_updated_permissions_grant_and_revoke() -> None:
    """Test grant and revoke in one call."""
    current = [Permission("read"), Permission("write")]
    result = _build_updated_permissions(
        current=current,
        grant=("network",),
        revoke=("write",),
    )
    result_strs = [str(p) for p in result]
    assert "read" in result_strs
    assert "network" in result_strs
    assert "write" not in result_strs


def test_build_updated_activity_config_idle_timeout() -> None:
    """Test changing just the idle timeout with a plain integer string."""
    current = ActivityConfig(
        idle_timeout_seconds=3600,
        activity_sources=(ActivitySource.CREATE, ActivitySource.BOOT),
    )
    result = _build_updated_activity_config(
        current=current,
        idle_timeout_str="300",
        idle_mode_str=None,
        activity_sources_str=None,
        add_activity_source=(),
        remove_activity_source=(),
    )
    assert result.idle_timeout_seconds == 300
    assert set(result.activity_sources) == {ActivitySource.CREATE, ActivitySource.BOOT}


def test_build_updated_activity_config_idle_timeout_duration_string() -> None:
    """Test changing idle timeout with a duration string like '5m'."""
    current = ActivityConfig(
        idle_timeout_seconds=3600,
        activity_sources=(ActivitySource.CREATE, ActivitySource.BOOT),
    )
    result = _build_updated_activity_config(
        current=current,
        idle_timeout_str="5m",
        idle_mode_str=None,
        activity_sources_str=None,
        add_activity_source=(),
        remove_activity_source=(),
    )
    assert result.idle_timeout_seconds == 300
    assert set(result.activity_sources) == {ActivitySource.CREATE, ActivitySource.BOOT}


def test_build_updated_activity_config_idle_mode() -> None:
    """Test changing the idle mode replaces activity sources with the mode's canonical set."""
    current = ActivityConfig(
        idle_timeout_seconds=3600,
        activity_sources=(ActivitySource.CREATE,),
    )
    result = _build_updated_activity_config(
        current=current,
        idle_timeout_str=None,
        idle_mode_str="disabled",
        activity_sources_str=None,
        add_activity_source=(),
        remove_activity_source=(),
    )
    assert result.idle_mode == IdleMode.DISABLED
    assert result.activity_sources == ()
    assert result.idle_timeout_seconds == 3600


def test_build_updated_activity_config_idle_mode_ssh() -> None:
    """Test that --idle-mode ssh sets the correct activity sources."""
    current = ActivityConfig(
        idle_timeout_seconds=3600,
        activity_sources=(ActivitySource.CREATE,),
    )
    result = _build_updated_activity_config(
        current=current,
        idle_timeout_str=None,
        idle_mode_str="ssh",
        activity_sources_str=None,
        add_activity_source=(),
        remove_activity_source=(),
    )
    assert result.idle_mode == IdleMode.SSH
    assert set(result.activity_sources) == {
        ActivitySource.SSH,
        ActivitySource.CREATE,
        ActivitySource.START,
        ActivitySource.BOOT,
    }


def test_build_updated_activity_config_replace_sources() -> None:
    """Test replacing activity sources entirely."""
    current = ActivityConfig(
        idle_timeout_seconds=3600,
        activity_sources=(ActivitySource.CREATE, ActivitySource.BOOT),
    )
    result = _build_updated_activity_config(
        current=current,
        idle_timeout_str=None,
        idle_mode_str=None,
        activity_sources_str="ssh,agent",
        add_activity_source=(),
        remove_activity_source=(),
    )
    assert set(result.activity_sources) == {ActivitySource.SSH, ActivitySource.AGENT}


def test_build_updated_activity_config_add_remove_source() -> None:
    """Test adding and removing activity sources."""
    current = ActivityConfig(
        idle_timeout_seconds=3600,
        activity_sources=(ActivitySource.CREATE, ActivitySource.BOOT),
    )
    result = _build_updated_activity_config(
        current=current,
        idle_timeout_str=None,
        idle_mode_str=None,
        activity_sources_str=None,
        add_activity_source=("ssh",),
        remove_activity_source=("boot",),
    )
    assert ActivitySource.SSH in result.activity_sources
    assert ActivitySource.CREATE in result.activity_sources
    assert ActivitySource.BOOT not in result.activity_sources


def test_activity_sources_mutually_exclusive_with_add_remove(
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test that --activity-sources cannot be combined with --add/--remove-activity-source."""
    result = cli_runner.invoke(
        limit,
        [
            "--all",
            "--activity-sources",
            "ssh,agent",
            "--add-activity-source",
            "boot",
        ],
        obj=plugin_manager,
        catch_exceptions=True,
    )

    assert result.exit_code != 0
    assert "Cannot combine --activity-sources with --add-activity-source" in result.output
