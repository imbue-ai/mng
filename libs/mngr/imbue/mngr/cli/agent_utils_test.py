"""Unit tests for agent_utils module."""

from unittest.mock import MagicMock
from unittest.mock import patch

import pytest

from imbue.mngr.cli.agent_utils import find_agent_by_name_or_id
from imbue.mngr.cli.agent_utils import select_agent_interactively_with_host
from imbue.mngr.errors import AgentNotFoundError
from imbue.mngr.errors import UserInputError
from imbue.mngr.interfaces.host import OnlineHostInterface
from imbue.mngr.primitives import AgentId
from imbue.mngr.primitives import AgentName
from imbue.mngr.primitives import AgentReference
from imbue.mngr.primitives import HostId
from imbue.mngr.primitives import HostName
from imbue.mngr.primitives import HostReference
from imbue.mngr.primitives import ProviderInstanceName


def _make_host_reference(
    provider: str = "local",
    host_id: HostId | None = None,
    host_name: str = "test-host",
) -> HostReference:
    """Create a HostReference for testing."""
    if host_id is None:
        host_id = HostId.generate()
    return HostReference(
        provider_name=ProviderInstanceName(provider),
        host_id=host_id,
        host_name=HostName(host_name),
    )


def _make_agent_reference(
    agent_id: AgentId,
    agent_name: str = "test-name",
    host_id: HostId | None = None,
    provider: str = "local",
) -> AgentReference:
    """Create an AgentReference for testing."""
    if host_id is None:
        host_id = HostId.generate()
    return AgentReference(
        agent_id=agent_id,
        agent_name=AgentName(agent_name),
        host_id=host_id,
        provider_name=ProviderInstanceName(provider),
    )


# =============================================================================
# find_agent_by_name_or_id tests
# =============================================================================


@patch("imbue.mngr.cli.agent_utils.get_provider_instance")
def test_find_agent_by_id_returns_matching_agent(mock_get_provider: MagicMock) -> None:
    agent_id = AgentId.generate()
    agent_name = AgentName("my-agent")

    # Set up mock agent
    mock_agent = MagicMock()
    mock_agent.id = agent_id
    mock_agent.name = agent_name

    # Set up mock host (use spec to pass isinstance check)
    mock_host = MagicMock(spec=OnlineHostInterface)
    mock_host.get_agents.return_value = [mock_agent]

    # Set up mock provider
    mock_provider = MagicMock()
    mock_provider.get_host.return_value = mock_host
    mock_get_provider.return_value = mock_provider

    # Set up agents_by_host
    host_ref = _make_host_reference()
    agent_ref = _make_agent_reference(agent_id=agent_id, agent_name=str(agent_name))
    agents_by_host = {host_ref: [agent_ref]}

    mock_ctx = MagicMock()

    result_agent, result_host = find_agent_by_name_or_id(str(agent_id), agents_by_host, mock_ctx)

    assert result_agent == mock_agent
    assert result_host == mock_host


@patch("imbue.mngr.cli.agent_utils.get_provider_instance")
def test_find_agent_by_name_returns_matching_agent(mock_get_provider: MagicMock) -> None:
    agent_id = AgentId.generate()
    agent_name = AgentName("my-agent")

    # Set up mock agent
    mock_agent = MagicMock()
    mock_agent.id = agent_id
    mock_agent.name = agent_name

    # Set up mock host (use spec to pass isinstance check)
    mock_host = MagicMock(spec=OnlineHostInterface)
    mock_host.get_agents.return_value = [mock_agent]

    # Set up mock provider
    mock_provider = MagicMock()
    mock_provider.get_host.return_value = mock_host
    mock_get_provider.return_value = mock_provider

    # Set up agents_by_host
    host_ref = _make_host_reference()
    agent_ref = _make_agent_reference(agent_id=agent_id, agent_name=str(agent_name))
    agents_by_host = {host_ref: [agent_ref]}

    mock_ctx = MagicMock()

    result_agent, result_host = find_agent_by_name_or_id(str(agent_name), agents_by_host, mock_ctx)

    assert result_agent == mock_agent
    assert result_host == mock_host


def test_find_agent_by_id_raises_when_not_found() -> None:
    agent_id = AgentId.generate()
    agents_by_host: dict[HostReference, list[AgentReference]] = {}
    mock_ctx = MagicMock()

    with pytest.raises(AgentNotFoundError):
        find_agent_by_name_or_id(str(agent_id), agents_by_host, mock_ctx)


def test_find_agent_by_name_raises_when_not_found() -> None:
    # Using an invalid ID format forces it to search by name
    agent_name = "non-existent-name"
    agents_by_host: dict[HostReference, list[AgentReference]] = {}
    mock_ctx = MagicMock()

    with pytest.raises(UserInputError, match="No agent found"):
        find_agent_by_name_or_id(agent_name, agents_by_host, mock_ctx)


@patch("imbue.mngr.cli.agent_utils.get_provider_instance")
def test_find_agent_by_name_raises_when_multiple_agents_match(mock_get_provider: MagicMock) -> None:
    agent_name = "shared-name"
    agent_id1 = AgentId.generate()
    agent_id2 = AgentId.generate()

    # Set up mock agents (two different agents with same name)
    mock_agent1 = MagicMock()
    mock_agent1.id = agent_id1
    mock_agent1.name = AgentName(agent_name)

    mock_agent2 = MagicMock()
    mock_agent2.id = agent_id2
    mock_agent2.name = AgentName(agent_name)

    # Set up mock hosts (use spec to pass isinstance check)
    mock_host1 = MagicMock(spec=OnlineHostInterface)
    mock_host1.get_agents.return_value = [mock_agent1]

    mock_host2 = MagicMock(spec=OnlineHostInterface)
    mock_host2.get_agents.return_value = [mock_agent2]

    # Set up mock provider to return different hosts
    mock_provider = MagicMock()
    mock_provider.get_host.side_effect = [mock_host1, mock_host2]
    mock_get_provider.return_value = mock_provider

    # Set up agents_by_host with two different hosts
    host_ref1 = _make_host_reference(host_id=HostId.generate())
    host_ref2 = _make_host_reference(host_id=HostId.generate())
    agent_ref1 = _make_agent_reference(agent_id=agent_id1, agent_name=agent_name)
    agent_ref2 = _make_agent_reference(agent_id=agent_id2, agent_name=agent_name)
    agents_by_host = {host_ref1: [agent_ref1], host_ref2: [agent_ref2]}

    mock_ctx = MagicMock()

    with pytest.raises(UserInputError, match="Multiple agents found"):
        find_agent_by_name_or_id(agent_name, agents_by_host, mock_ctx)


@patch("imbue.mngr.cli.agent_utils.get_provider_instance")
def test_find_agent_by_name_skips_offline_hosts(mock_get_provider: MagicMock) -> None:
    agent_name = "my-agent"
    agent_id = AgentId.generate()

    # Set up mock provider that returns a non-OnlineHostInterface
    mock_offline_host = MagicMock()
    # Make isinstance check fail by not being an OnlineHostInterface
    mock_offline_host.__class__.__name__ = "OfflineHost"

    mock_provider = MagicMock()
    mock_provider.get_host.return_value = mock_offline_host
    mock_get_provider.return_value = mock_provider

    # Mock the isinstance check
    with patch("imbue.mngr.cli.agent_utils.isinstance", return_value=False):
        # Set up agents_by_host
        host_ref = _make_host_reference()
        agent_ref = _make_agent_reference(agent_id=agent_id, agent_name=agent_name)
        agents_by_host = {host_ref: [agent_ref]}

        mock_ctx = MagicMock()

        with pytest.raises(UserInputError, match="No agent found"):
            find_agent_by_name_or_id(agent_name, agents_by_host, mock_ctx)


# =============================================================================
# select_agent_interactively_with_host tests
# =============================================================================


@patch("imbue.mngr.cli.agent_utils.list_agents")
def test_select_agent_interactively_raises_when_no_agents(mock_list_agents: MagicMock) -> None:
    mock_result = MagicMock()
    mock_result.agents = []
    mock_list_agents.return_value = mock_result

    mock_ctx = MagicMock()

    with pytest.raises(UserInputError, match="No agents found"):
        select_agent_interactively_with_host(mock_ctx)


@patch("imbue.mngr.cli.agent_utils.find_agent_by_name_or_id")
@patch("imbue.mngr.cli.agent_utils.load_all_agents_grouped_by_host")
@patch("imbue.mngr.cli.agent_utils.select_agent_interactively")
@patch("imbue.mngr.cli.agent_utils.list_agents")
def test_select_agent_interactively_returns_none_when_user_quits(
    mock_list_agents: MagicMock,
    mock_select: MagicMock,
    mock_load_agents: MagicMock,
    mock_find_agent: MagicMock,
) -> None:
    mock_result = MagicMock()
    mock_result.agents = [MagicMock()]
    mock_list_agents.return_value = mock_result

    # User quits without selecting
    mock_select.return_value = None

    mock_ctx = MagicMock()

    result = select_agent_interactively_with_host(mock_ctx)

    assert result is None
    mock_find_agent.assert_not_called()


@patch("imbue.mngr.cli.agent_utils.find_agent_by_name_or_id")
@patch("imbue.mngr.cli.agent_utils.load_all_agents_grouped_by_host")
@patch("imbue.mngr.cli.agent_utils.select_agent_interactively")
@patch("imbue.mngr.cli.agent_utils.list_agents")
def test_select_agent_interactively_returns_selected_agent(
    mock_list_agents: MagicMock,
    mock_select: MagicMock,
    mock_load_agents: MagicMock,
    mock_find_agent: MagicMock,
) -> None:
    mock_result = MagicMock()
    mock_result.agents = [MagicMock()]
    mock_list_agents.return_value = mock_result

    # User selects an agent
    selected_agent = MagicMock()
    selected_agent.id = AgentId.generate()
    mock_select.return_value = selected_agent

    # Set up the agents_by_host return value
    mock_load_agents.return_value = ({}, [])

    # Set up the final agent/host return value
    final_agent = MagicMock()
    final_host = MagicMock()
    mock_find_agent.return_value = (final_agent, final_host)

    mock_ctx = MagicMock()

    result = select_agent_interactively_with_host(mock_ctx)

    assert result == (final_agent, final_host)
    mock_find_agent.assert_called_once()
