"""Tests for create module helper functions."""

from unittest.mock import MagicMock
from unittest.mock import patch

from imbue.mngr.cli.create import _parse_host_lifecycle_options
from imbue.mngr.cli.create import _try_reuse_existing_agent
from imbue.mngr.primitives import ActivitySource
from imbue.mngr.primitives import AgentId
from imbue.mngr.primitives import AgentName
from imbue.mngr.primitives import AgentReference
from imbue.mngr.primitives import HostId
from imbue.mngr.primitives import HostName
from imbue.mngr.primitives import HostReference
from imbue.mngr.primitives import IdleMode
from imbue.mngr.primitives import ProviderInstanceName


def test_parse_host_lifecycle_options_all_none() -> None:
    """When all CLI options are None, result should have all None values."""
    opts = MagicMock()
    opts.idle_timeout = None
    opts.idle_mode = None
    opts.activity_sources = None

    result = _parse_host_lifecycle_options(opts)

    assert result.idle_timeout_seconds is None
    assert result.idle_mode is None
    assert result.activity_sources is None


def test_parse_host_lifecycle_options_with_idle_timeout() -> None:
    """idle_timeout should be passed through directly."""
    opts = MagicMock()
    opts.idle_timeout = 600
    opts.idle_mode = None
    opts.activity_sources = None

    result = _parse_host_lifecycle_options(opts)

    assert result.idle_timeout_seconds == 600
    assert result.idle_mode is None
    assert result.activity_sources is None


def test_parse_host_lifecycle_options_with_idle_mode_lowercase() -> None:
    """idle_mode should be parsed and uppercased to IdleMode enum."""
    opts = MagicMock()
    opts.idle_timeout = None
    opts.idle_mode = "agent"
    opts.activity_sources = None

    result = _parse_host_lifecycle_options(opts)

    assert result.idle_timeout_seconds is None
    assert result.idle_mode == IdleMode.AGENT
    assert result.activity_sources is None


def test_parse_host_lifecycle_options_with_idle_mode_uppercase() -> None:
    """idle_mode should work with uppercase input."""
    opts = MagicMock()
    opts.idle_timeout = None
    opts.idle_mode = "SSH"
    opts.activity_sources = None

    result = _parse_host_lifecycle_options(opts)

    assert result.idle_mode == IdleMode.SSH


def test_parse_host_lifecycle_options_with_activity_sources_single() -> None:
    """activity_sources should parse a single source."""
    opts = MagicMock()
    opts.idle_timeout = None
    opts.idle_mode = None
    opts.activity_sources = "boot"

    result = _parse_host_lifecycle_options(opts)

    assert result.activity_sources == (ActivitySource.BOOT,)


def test_parse_host_lifecycle_options_with_activity_sources_multiple() -> None:
    """activity_sources should parse comma-separated sources."""
    opts = MagicMock()
    opts.idle_timeout = None
    opts.idle_mode = None
    opts.activity_sources = "boot,ssh,agent"

    result = _parse_host_lifecycle_options(opts)

    assert result.activity_sources == (ActivitySource.BOOT, ActivitySource.SSH, ActivitySource.AGENT)


def test_parse_host_lifecycle_options_with_activity_sources_whitespace() -> None:
    """activity_sources should handle whitespace around commas."""
    opts = MagicMock()
    opts.idle_timeout = None
    opts.idle_mode = None
    opts.activity_sources = "boot , ssh , agent"

    result = _parse_host_lifecycle_options(opts)

    assert result.activity_sources == (ActivitySource.BOOT, ActivitySource.SSH, ActivitySource.AGENT)


def test_parse_host_lifecycle_options_all_provided() -> None:
    """All options should be correctly parsed when all are provided."""
    opts = MagicMock()
    opts.idle_timeout = 1800
    opts.idle_mode = "disabled"
    opts.activity_sources = "create,process"

    result = _parse_host_lifecycle_options(opts)

    assert result.idle_timeout_seconds == 1800
    assert result.idle_mode == IdleMode.DISABLED
    assert result.activity_sources == (ActivitySource.CREATE, ActivitySource.PROCESS)


# Tests for _try_reuse_existing_agent

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


def test_try_reuse_existing_agent_no_agents_found() -> None:
    """Returns None when no agents match the name."""
    mngr_ctx = MagicMock()
    agent_and_host_loader = MagicMock(return_value={})

    result = _try_reuse_existing_agent(
        agent_name=AgentName("nonexistent"),
        provider_name=None,
        target_host_ref=None,
        mngr_ctx=mngr_ctx,
        agent_and_host_loader=agent_and_host_loader,
    )

    assert result is None


def test_try_reuse_existing_agent_no_matching_name() -> None:
    """Returns None when agents exist but none match the name."""
    mngr_ctx = MagicMock()
    host_ref = _make_host_ref()
    agent_ref = _make_agent_ref(agent_name="other-agent")

    agent_and_host_loader = MagicMock(return_value={host_ref: [agent_ref]})

    result = _try_reuse_existing_agent(
        agent_name=AgentName("test-agent"),
        provider_name=None,
        target_host_ref=None,
        mngr_ctx=mngr_ctx,
        agent_and_host_loader=agent_and_host_loader,
    )

    assert result is None


def test_try_reuse_existing_agent_filters_by_provider() -> None:
    """Returns None when agent exists but on different provider."""
    mngr_ctx = MagicMock()
    host_ref = _make_host_ref(provider="modal")
    agent_ref = _make_agent_ref(agent_name="test-agent", provider="modal")

    agent_and_host_loader = MagicMock(return_value={host_ref: [agent_ref]})

    # Filtering by "local" provider should not find the agent on "modal"
    result = _try_reuse_existing_agent(
        agent_name=AgentName("test-agent"),
        provider_name=ProviderInstanceName("local"),
        target_host_ref=None,
        mngr_ctx=mngr_ctx,
        agent_and_host_loader=agent_and_host_loader,
    )

    assert result is None


def test_try_reuse_existing_agent_filters_by_host() -> None:
    """Returns None when agent exists but on different host."""
    mngr_ctx = MagicMock()
    host_ref = _make_host_ref(host_id=TEST_HOST_ID_1)
    agent_ref = _make_agent_ref(agent_name="test-agent", host_id=TEST_HOST_ID_1)

    agent_and_host_loader = MagicMock(return_value={host_ref: [agent_ref]})

    # Create a different target host reference
    target_host_ref = _make_host_ref(host_id=TEST_HOST_ID_2)

    result = _try_reuse_existing_agent(
        agent_name=AgentName("test-agent"),
        provider_name=None,
        target_host_ref=target_host_ref,
        mngr_ctx=mngr_ctx,
        agent_and_host_loader=agent_and_host_loader,
    )

    assert result is None


@patch("imbue.mngr.cli.create.ensure_agent_started")
@patch("imbue.mngr.cli.create.ensure_host_started")
@patch("imbue.mngr.cli.create.get_provider_instance")
def test_try_reuse_existing_agent_found_and_started(
    mock_get_provider: MagicMock,
    mock_ensure_host_started: MagicMock,
    mock_ensure_agent_started: MagicMock,
) -> None:
    """Returns (agent, host) when agent is found and started."""
    mngr_ctx = MagicMock()
    host_ref = _make_host_ref()
    agent_ref = _make_agent_ref(agent_name="test-agent")

    agent_and_host_loader = MagicMock(return_value={host_ref: [agent_ref]})

    # Setup mocks
    mock_provider = MagicMock()
    mock_get_provider.return_value = mock_provider
    mock_host = MagicMock()
    mock_provider.get_host.return_value = mock_host
    mock_online_host = MagicMock()
    mock_ensure_host_started.return_value = (mock_online_host, False)

    # Setup mock agent with matching ID
    mock_agent = MagicMock()
    mock_agent.id = AgentId(TEST_AGENT_ID_1)
    mock_online_host.get_agents.return_value = [mock_agent]

    result = _try_reuse_existing_agent(
        agent_name=AgentName("test-agent"),
        provider_name=None,
        target_host_ref=None,
        mngr_ctx=mngr_ctx,
        agent_and_host_loader=agent_and_host_loader,
    )

    assert result is not None
    agent, host = result
    assert agent == mock_agent
    assert host == mock_online_host
    mock_ensure_agent_started.assert_called_once_with(mock_agent, mock_online_host, is_start_desired=True)


@patch("imbue.mngr.cli.create.ensure_host_started")
@patch("imbue.mngr.cli.create.get_provider_instance")
def test_try_reuse_existing_agent_not_found_on_host(
    mock_get_provider: MagicMock,
    mock_ensure_host_started: MagicMock,
) -> None:
    """Returns None when agent reference exists but agent not found on online host."""
    mngr_ctx = MagicMock()
    host_ref = _make_host_ref()
    agent_ref = _make_agent_ref(agent_name="test-agent")

    agent_and_host_loader = MagicMock(return_value={host_ref: [agent_ref]})

    # Setup mocks
    mock_provider = MagicMock()
    mock_get_provider.return_value = mock_provider
    mock_host = MagicMock()
    mock_provider.get_host.return_value = mock_host
    mock_online_host = MagicMock()
    mock_ensure_host_started.return_value = (mock_online_host, False)

    # Agent not found on online host (empty list)
    mock_online_host.get_agents.return_value = []

    result = _try_reuse_existing_agent(
        agent_name=AgentName("test-agent"),
        provider_name=None,
        target_host_ref=None,
        mngr_ctx=mngr_ctx,
        agent_and_host_loader=agent_and_host_loader,
    )

    assert result is None
