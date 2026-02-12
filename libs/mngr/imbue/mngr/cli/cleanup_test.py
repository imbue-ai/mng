"""Unit tests for cleanup CLI helpers."""

from datetime import datetime
from datetime import timezone
from pathlib import Path

import pluggy
from click.testing import CliRunner

from imbue.mngr.api.list import AgentInfo
from imbue.mngr.cli.cleanup import CleanupCliOptions
from imbue.mngr.cli.cleanup import _build_cel_filters_from_options
from imbue.mngr.cli.cleanup import _parse_selection
from imbue.mngr.cli.cleanup import cleanup
from imbue.mngr.interfaces.data_types import HostInfo
from imbue.mngr.primitives import AgentId
from imbue.mngr.primitives import AgentLifecycleState
from imbue.mngr.primitives import AgentName
from imbue.mngr.primitives import CommandString
from imbue.mngr.primitives import HostId
from imbue.mngr.primitives import ProviderInstanceName

# =============================================================================
# Helper for creating test AgentInfo objects
# =============================================================================


def _make_agent_info(name: str = "test-agent") -> AgentInfo:
    """Create a minimal AgentInfo for testing."""
    return AgentInfo(
        id=AgentId.generate(),
        name=AgentName(name),
        type="claude",
        command=CommandString("claude"),
        work_dir=Path("/work"),
        create_time=datetime.now(timezone.utc),
        start_on_boot=False,
        state=AgentLifecycleState.RUNNING,
        host=HostInfo(
            id=HostId.generate(),
            name="test-host",
            provider_name=ProviderInstanceName("local"),
        ),
    )


# =============================================================================
# Tests for _build_cel_filters_from_options
# =============================================================================


def _make_opts(
    force: bool = False,
    dry_run: bool = False,
    include: tuple[str, ...] = (),
    exclude: tuple[str, ...] = (),
    older_than: str | None = None,
    idle_for: str | None = None,
    tag: tuple[str, ...] = (),
    provider: tuple[str, ...] = (),
    agent_type: tuple[str, ...] = (),
    action: str = "destroy",
    snapshot_before: bool = False,
) -> CleanupCliOptions:
    """Create a CleanupCliOptions with defaults and specified overrides."""
    return CleanupCliOptions(
        force=force,
        dry_run=dry_run,
        include=include,
        exclude=exclude,
        older_than=older_than,
        idle_for=idle_for,
        tag=tag,
        provider=provider,
        agent_type=agent_type,
        action=action,
        snapshot_before=snapshot_before,
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


def test_build_cel_filters_no_options() -> None:
    opts = _make_opts()
    include_filters, exclude_filters = _build_cel_filters_from_options(opts)
    assert include_filters == []
    assert exclude_filters == []


def test_build_cel_filters_older_than() -> None:
    opts = _make_opts(older_than="7d")
    include_filters, exclude_filters = _build_cel_filters_from_options(opts)
    assert "age > 604800.0" in include_filters
    assert exclude_filters == []


def test_build_cel_filters_idle_for() -> None:
    opts = _make_opts(idle_for="1h")
    include_filters, exclude_filters = _build_cel_filters_from_options(opts)
    assert "idle > 3600.0" in include_filters


def test_build_cel_filters_single_provider() -> None:
    opts = _make_opts(provider=("docker",))
    include_filters, exclude_filters = _build_cel_filters_from_options(opts)
    assert 'host.provider == "docker"' in include_filters


def test_build_cel_filters_multiple_providers() -> None:
    opts = _make_opts(provider=("docker", "modal"))
    include_filters, exclude_filters = _build_cel_filters_from_options(opts)
    assert any("docker" in f and "modal" in f for f in include_filters)


def test_build_cel_filters_single_agent_type() -> None:
    opts = _make_opts(agent_type=("claude",))
    include_filters, exclude_filters = _build_cel_filters_from_options(opts)
    assert 'type == "claude"' in include_filters


def test_build_cel_filters_multiple_agent_types() -> None:
    opts = _make_opts(agent_type=("claude", "codex"))
    include_filters, exclude_filters = _build_cel_filters_from_options(opts)
    assert any("claude" in f and "codex" in f for f in include_filters)


def test_build_cel_filters_tag_with_value() -> None:
    opts = _make_opts(tag=("env=prod",))
    include_filters, exclude_filters = _build_cel_filters_from_options(opts)
    assert 'host.tags.env == "prod"' in include_filters


def test_build_cel_filters_tag_without_value() -> None:
    opts = _make_opts(tag=("ephemeral",))
    include_filters, exclude_filters = _build_cel_filters_from_options(opts)
    assert 'host.tags.ephemeral == "true"' in include_filters


def test_build_cel_filters_include_and_exclude_passthrough() -> None:
    opts = _make_opts(include=('state == "RUNNING"',), exclude=('name == "keep"',))
    include_filters, exclude_filters = _build_cel_filters_from_options(opts)
    assert 'state == "RUNNING"' in include_filters
    assert 'name == "keep"' in exclude_filters


def test_build_cel_filters_combined() -> None:
    opts = _make_opts(older_than="7d", provider=("docker",), agent_type=("claude",))
    include_filters, exclude_filters = _build_cel_filters_from_options(opts)
    assert len(include_filters) == 3
    assert "age > 604800.0" in include_filters
    assert 'host.provider == "docker"' in include_filters
    assert 'type == "claude"' in include_filters


# =============================================================================
# Tests for _parse_selection
# =============================================================================


def test_parse_selection_none() -> None:
    agents = [_make_agent_info("a"), _make_agent_info("b")]
    assert _parse_selection("none", agents) == []


def test_parse_selection_empty() -> None:
    agents = [_make_agent_info("a")]
    assert _parse_selection("", agents) == []


def test_parse_selection_all() -> None:
    agents = [_make_agent_info("a"), _make_agent_info("b")]
    result = _parse_selection("all", agents)
    assert len(result) == 2


def test_parse_selection_single_number() -> None:
    agents = [_make_agent_info("a"), _make_agent_info("b"), _make_agent_info("c")]
    result = _parse_selection("2", agents)
    assert len(result) == 1
    assert result[0].name == AgentName("b")


def test_parse_selection_comma_separated() -> None:
    agents = [_make_agent_info("a"), _make_agent_info("b"), _make_agent_info("c")]
    result = _parse_selection("1,3", agents)
    assert len(result) == 2
    assert result[0].name == AgentName("a")
    assert result[1].name == AgentName("c")


def test_parse_selection_range() -> None:
    agents = [_make_agent_info("a"), _make_agent_info("b"), _make_agent_info("c")]
    result = _parse_selection("1-3", agents)
    assert len(result) == 3


def test_parse_selection_mixed() -> None:
    agents = [_make_agent_info(f"agent-{i}") for i in range(5)]
    result = _parse_selection("1,3-5", agents)
    assert len(result) == 4


def test_parse_selection_out_of_range_ignored() -> None:
    agents = [_make_agent_info("a"), _make_agent_info("b")]
    result = _parse_selection("1,5,10", agents)
    assert len(result) == 1


def test_parse_selection_invalid_input_ignored() -> None:
    agents = [_make_agent_info("a")]
    result = _parse_selection("abc", agents)
    assert result == []


# =============================================================================
# Tests for CLI options model
# =============================================================================


def test_cleanup_cli_options_fields() -> None:
    opts = _make_opts()
    assert opts.force is False
    assert opts.dry_run is False
    assert opts.action == "destroy"
    assert opts.older_than is None
    assert opts.idle_for is None
    assert opts.tag == ()
    assert opts.provider == ()
    assert opts.agent_type == ()
    assert opts.snapshot_before is False


# =============================================================================
# Tests for CLI command invocation
# =============================================================================


def test_cleanup_help_exits_zero(
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test that --help works and exits 0."""
    result = cli_runner.invoke(
        cleanup,
        ["--help"],
        obj=plugin_manager,
        catch_exceptions=False,
    )
    assert result.exit_code == 0
    assert "cleanup" in result.output.lower()


def test_cleanup_dry_run_yes_no_agents(
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test that --dry-run --yes with no agents reports none found."""
    result = cli_runner.invoke(
        cleanup,
        ["--dry-run", "--yes"],
        obj=plugin_manager,
        catch_exceptions=False,
    )
    assert result.exit_code == 0
    assert "no agents found" in result.output.lower()


def test_cleanup_snapshot_before_raises_not_implemented(
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test that --snapshot-before raises NotImplementedError."""
    result = cli_runner.invoke(
        cleanup,
        ["--snapshot-before", "--yes"],
        obj=plugin_manager,
        catch_exceptions=True,
    )
    assert result.exit_code != 0
