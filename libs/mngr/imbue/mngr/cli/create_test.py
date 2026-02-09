"""Tests for create module helper functions."""

from pathlib import Path
from typing import cast

import pytest

from imbue.mngr.cli.create import CreateCliOptions
from imbue.mngr.cli.create import _parse_host_lifecycle_options
from imbue.mngr.cli.create import _try_reuse_existing_agent
from imbue.mngr.config.data_types import MngrContext
from imbue.mngr.interfaces.host import CreateAgentOptions
from imbue.mngr.interfaces.host import OnlineHostInterface
from imbue.mngr.primitives import ActivitySource
from imbue.mngr.primitives import AgentId
from imbue.mngr.primitives import AgentName
from imbue.mngr.primitives import AgentReference
from imbue.mngr.primitives import AgentTypeName
from imbue.mngr.primitives import CommandString
from imbue.mngr.primitives import HostId
from imbue.mngr.primitives import HostName
from imbue.mngr.primitives import HostReference
from imbue.mngr.primitives import IdleMode
from imbue.mngr.primitives import ProviderInstanceName
from imbue.mngr.providers.local.instance import LocalProviderInstance

# =============================================================================
# Shared fixture: baseline CreateCliOptions with sensible defaults
# =============================================================================


@pytest.fixture
def default_create_cli_opts() -> CreateCliOptions:
    """Baseline CreateCliOptions with sensible defaults for all fields.

    Tests use .model_copy(update={...}) to override only the fields relevant
    to each test case.
    """
    return CreateCliOptions(
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
        positional_name=None,
        positional_agent_type=None,
        agent_args=(),
        template=(),
        agent_type=None,
        reuse=False,
        connect=True,
        await_ready=None,
        await_agent_stopped=None,
        copy_work_dir=None,
        ensure_clean=True,
        snapshot_source=None,
        name=None,
        name_style="english",
        agent_command=None,
        add_command=(),
        user=None,
        source=None,
        source_agent=None,
        source_host=None,
        source_path=None,
        target=None,
        target_path=None,
        in_place=False,
        copy_source=False,
        clone=False,
        worktree=False,
        rsync=None,
        rsync_args=None,
        include_git=True,
        include_unclean=None,
        include_gitignored=False,
        base_branch=None,
        new_branch="",
        new_branch_prefix="mngr/",
        depth=None,
        shallow_since=None,
        agent_env=(),
        agent_env_file=(),
        pass_agent_env=(),
        host=None,
        new_host=None,
        host_name=None,
        host_name_style="astronomy",
        tag=(),
        project=None,
        host_env=(),
        host_env_file=(),
        pass_host_env=(),
        known_host=(),
        snapshot=None,
        build_arg=(),
        build_args=None,
        start_arg=(),
        start_args=None,
        reconnect=True,
        interactive=None,
        message=None,
        message_file=None,
        edit_message=False,
        resume_message=None,
        resume_message_file=None,
        retry=3,
        retry_delay="5s",
        attach_command=None,
        idle_timeout=None,
        idle_mode=None,
        activity_sources=None,
        start_on_boot=None,
        grant=(),
        user_command=(),
        sudo_command=(),
        upload_file=(),
        append_to_file=(),
        prepend_to_file=(),
        create_directory=(),
        ready_timeout=10.0,
    )


# =============================================================================
# Tests for _parse_host_lifecycle_options
# =============================================================================


def test_parse_host_lifecycle_options_all_none(default_create_cli_opts: CreateCliOptions) -> None:
    """When all CLI options are None, result should have all None values."""
    result = _parse_host_lifecycle_options(default_create_cli_opts)

    assert result.idle_timeout_seconds is None
    assert result.idle_mode is None
    assert result.activity_sources is None


def test_parse_host_lifecycle_options_with_idle_timeout(default_create_cli_opts: CreateCliOptions) -> None:
    """idle_timeout should be passed through directly."""
    opts = default_create_cli_opts.model_copy(update={"idle_timeout": 600})

    result = _parse_host_lifecycle_options(opts)

    assert result.idle_timeout_seconds == 600
    assert result.idle_mode is None
    assert result.activity_sources is None


def test_parse_host_lifecycle_options_with_idle_mode_lowercase(default_create_cli_opts: CreateCliOptions) -> None:
    """idle_mode should be parsed and uppercased to IdleMode enum."""
    opts = default_create_cli_opts.model_copy(update={"idle_mode": "agent"})

    result = _parse_host_lifecycle_options(opts)

    assert result.idle_timeout_seconds is None
    assert result.idle_mode == IdleMode.AGENT
    assert result.activity_sources is None


def test_parse_host_lifecycle_options_with_idle_mode_uppercase(default_create_cli_opts: CreateCliOptions) -> None:
    """idle_mode should work with uppercase input."""
    opts = default_create_cli_opts.model_copy(update={"idle_mode": "SSH"})

    result = _parse_host_lifecycle_options(opts)

    assert result.idle_mode == IdleMode.SSH


def test_parse_host_lifecycle_options_with_activity_sources_single(default_create_cli_opts: CreateCliOptions) -> None:
    """activity_sources should parse a single source."""
    opts = default_create_cli_opts.model_copy(update={"activity_sources": "boot"})

    result = _parse_host_lifecycle_options(opts)

    assert result.activity_sources == (ActivitySource.BOOT,)


def test_parse_host_lifecycle_options_with_activity_sources_multiple(
    default_create_cli_opts: CreateCliOptions,
) -> None:
    """activity_sources should parse comma-separated sources."""
    opts = default_create_cli_opts.model_copy(update={"activity_sources": "boot,ssh,agent"})

    result = _parse_host_lifecycle_options(opts)

    assert result.activity_sources == (ActivitySource.BOOT, ActivitySource.SSH, ActivitySource.AGENT)


def test_parse_host_lifecycle_options_with_activity_sources_whitespace(
    default_create_cli_opts: CreateCliOptions,
) -> None:
    """activity_sources should handle whitespace around commas."""
    opts = default_create_cli_opts.model_copy(update={"activity_sources": "boot , ssh , agent"})

    result = _parse_host_lifecycle_options(opts)

    assert result.activity_sources == (ActivitySource.BOOT, ActivitySource.SSH, ActivitySource.AGENT)


def test_parse_host_lifecycle_options_all_provided(default_create_cli_opts: CreateCliOptions) -> None:
    """All options should be correctly parsed when all are provided."""
    opts = default_create_cli_opts.model_copy(
        update={
            "idle_timeout": 1800,
            "idle_mode": "disabled",
            "activity_sources": "create,process",
        }
    )

    result = _parse_host_lifecycle_options(opts)

    assert result.idle_timeout_seconds == 1800
    assert result.idle_mode == IdleMode.DISABLED
    assert result.activity_sources == (ActivitySource.CREATE, ActivitySource.PROCESS)


# =============================================================================
# Tests for _try_reuse_existing_agent
# =============================================================================

# Valid 32-character hex strings for test IDs
TEST_HOST_ID_1 = "host-00000000000000000000000000000001"
TEST_HOST_ID_2 = "host-00000000000000000000000000000002"
TEST_AGENT_ID_1 = "agent-00000000000000000000000000000001"
TEST_AGENT_ID_2 = "agent-00000000000000000000000000000002"


def _make_host_ref(
    provider: str = "local", host_id: str = TEST_HOST_ID_1, host_name: str = "test-host"
) -> HostReference:
    return HostReference(
        provider_name=ProviderInstanceName(provider),
        host_id=HostId(host_id),
        host_name=HostName(host_name),
    )


def _make_agent_ref(
    agent_id: str = TEST_AGENT_ID_1,
    agent_name: str = "test-agent",
    host_id: str = TEST_HOST_ID_1,
    provider: str = "local",
) -> AgentReference:
    return AgentReference(
        agent_id=AgentId(agent_id),
        agent_name=AgentName(agent_name),
        host_id=HostId(host_id),
        provider_name=ProviderInstanceName(provider),
    )


# -- Filtering tests (function returns early, no provider/host interaction) --


def test_try_reuse_existing_agent_no_agents_found(temp_mngr_ctx: MngrContext) -> None:
    """Returns None when no agents match the name."""
    result = _try_reuse_existing_agent(
        agent_name=AgentName("nonexistent"),
        provider_name=None,
        target_host_ref=None,
        mngr_ctx=temp_mngr_ctx,
        agent_and_host_loader=lambda: {},
    )

    assert result is None


def test_try_reuse_existing_agent_no_matching_name(temp_mngr_ctx: MngrContext) -> None:
    """Returns None when agents exist but none match the name."""
    host_ref = _make_host_ref()
    agent_ref = _make_agent_ref(agent_name="other-agent")

    result = _try_reuse_existing_agent(
        agent_name=AgentName("test-agent"),
        provider_name=None,
        target_host_ref=None,
        mngr_ctx=temp_mngr_ctx,
        agent_and_host_loader=lambda: {host_ref: [agent_ref]},
    )

    assert result is None


def test_try_reuse_existing_agent_filters_by_provider(temp_mngr_ctx: MngrContext) -> None:
    """Returns None when agent exists but on different provider."""
    host_ref = _make_host_ref(provider="modal")
    agent_ref = _make_agent_ref(agent_name="test-agent", provider="modal")

    result = _try_reuse_existing_agent(
        agent_name=AgentName("test-agent"),
        provider_name=ProviderInstanceName("local"),
        target_host_ref=None,
        mngr_ctx=temp_mngr_ctx,
        agent_and_host_loader=lambda: {host_ref: [agent_ref]},
    )

    assert result is None


def test_try_reuse_existing_agent_filters_by_host(temp_mngr_ctx: MngrContext) -> None:
    """Returns None when agent exists but on different host."""
    host_ref = _make_host_ref(host_id=TEST_HOST_ID_1)
    agent_ref = _make_agent_ref(agent_name="test-agent", host_id=TEST_HOST_ID_1)

    target_host_ref = _make_host_ref(host_id=TEST_HOST_ID_2)

    result = _try_reuse_existing_agent(
        agent_name=AgentName("test-agent"),
        provider_name=None,
        target_host_ref=target_host_ref,
        mngr_ctx=temp_mngr_ctx,
        agent_and_host_loader=lambda: {host_ref: [agent_ref]},
    )

    assert result is None


# -- Tests using real local provider infrastructure --


def test_try_reuse_existing_agent_found_and_started(
    local_provider: LocalProviderInstance,
    temp_mngr_ctx: MngrContext,
    temp_work_dir: Path,
) -> None:
    """Returns (agent, host) when agent is found and started."""
    local_host = cast(OnlineHostInterface, local_provider.get_host(HostName("local")))

    # Create a real agent on the local host with a harmless command
    agent_options = CreateAgentOptions(
        agent_type=AgentTypeName("generic"),
        name=AgentName("reuse-test-agent"),
        command=CommandString("sleep 47291"),
    )
    agent = local_host.create_agent_state(
        work_dir_path=temp_work_dir,
        options=agent_options,
    )

    # Build references that match the real host and agent
    host_ref = HostReference(
        provider_name=ProviderInstanceName("local"),
        host_id=local_host.id,
        host_name=local_host.get_name(),
    )
    agent_ref = AgentReference(
        agent_id=agent.id,
        agent_name=agent.name,
        host_id=local_host.id,
        provider_name=ProviderInstanceName("local"),
    )

    try:
        result = _try_reuse_existing_agent(
            agent_name=agent.name,
            provider_name=None,
            target_host_ref=None,
            mngr_ctx=temp_mngr_ctx,
            agent_and_host_loader=lambda: {host_ref: [agent_ref]},
        )

        assert result is not None
        found_agent, found_host = result
        assert found_agent.id == agent.id
        assert found_agent.name == agent.name
        assert found_host.id == local_host.id
    finally:
        local_host.stop_agents([agent.id])


def test_try_reuse_existing_agent_not_found_on_host(
    local_provider: LocalProviderInstance,
    temp_mngr_ctx: MngrContext,
) -> None:
    """Returns None when agent reference exists but agent not found on online host."""
    local_host = cast(OnlineHostInterface, local_provider.get_host(HostName("local")))

    # Build references pointing to this host, but with a nonexistent agent ID
    host_ref = HostReference(
        provider_name=ProviderInstanceName("local"),
        host_id=local_host.id,
        host_name=local_host.get_name(),
    )
    agent_ref = AgentReference(
        agent_id=AgentId(TEST_AGENT_ID_1),
        agent_name=AgentName("ghost-agent"),
        host_id=local_host.id,
        provider_name=ProviderInstanceName("local"),
    )

    result = _try_reuse_existing_agent(
        agent_name=AgentName("ghost-agent"),
        provider_name=None,
        target_host_ref=None,
        mngr_ctx=temp_mngr_ctx,
        agent_and_host_loader=lambda: {host_ref: [agent_ref]},
    )

    assert result is None
