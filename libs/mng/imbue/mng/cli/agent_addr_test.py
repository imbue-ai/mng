"""Tests for agent address parsing and resolution utilities."""

from imbue.mng.api.find import AgentMatch
from imbue.mng.cli.agent_addr import AgentAddress
from imbue.mng.cli.agent_addr import _address_matches_agent_match
from imbue.mng.cli.agent_addr import _address_matches_host
from imbue.mng.cli.agent_addr import filter_agents_by_host_constraint
from imbue.mng.cli.agent_addr import parse_identifier_as_address
from imbue.mng.primitives import AgentId
from imbue.mng.primitives import AgentName
from imbue.mng.primitives import DiscoveredAgent
from imbue.mng.primitives import DiscoveredHost
from imbue.mng.primitives import HostId
from imbue.mng.primitives import HostName
from imbue.mng.primitives import ProviderInstanceName

# =============================================================================
# parse_identifier_as_address tests
# =============================================================================


def test_parse_identifier_plain_name() -> None:
    """A plain name returns the string unchanged and a name-only address."""
    ident, addr = parse_identifier_as_address("my-agent")

    assert ident == "my-agent"
    assert addr.agent_name == AgentName("my-agent")
    assert addr.host_name is None
    assert addr.provider_name is None


def test_parse_identifier_with_host() -> None:
    """NAME@HOST extracts the name and sets host in the address."""
    ident, addr = parse_identifier_as_address("my-agent@myhost")

    assert ident == "my-agent"
    assert addr.agent_name == AgentName("my-agent")
    assert addr.host_name == HostName("myhost")
    assert addr.provider_name is None


def test_parse_identifier_with_host_and_provider() -> None:
    """NAME@HOST.PROVIDER extracts name and sets host+provider."""
    ident, addr = parse_identifier_as_address("my-agent@myhost.modal")

    assert ident == "my-agent"
    assert addr.host_name == HostName("myhost")
    assert addr.provider_name == ProviderInstanceName("modal")


def test_parse_identifier_with_provider_only() -> None:
    """NAME@.PROVIDER extracts name and sets provider."""
    ident, addr = parse_identifier_as_address("my-agent@.modal")

    assert ident == "my-agent"
    assert addr.host_name is None
    assert addr.provider_name == ProviderInstanceName("modal")


# =============================================================================
# _address_matches_host tests
# =============================================================================


def _make_host(name: str = "myhost", provider: str = "local") -> DiscoveredHost:
    return DiscoveredHost(
        host_id=HostId.generate(),
        host_name=HostName(name),
        provider_name=ProviderInstanceName(provider),
    )


def test_address_matches_host_no_constraints() -> None:
    """An address with no host component matches any host."""
    address = AgentAddress()
    host = _make_host()

    assert _address_matches_host(address, host) is True


def test_address_matches_host_by_name() -> None:
    """An address with host_name matches hosts with that name."""
    address = AgentAddress(host_name=HostName("myhost"))

    assert _address_matches_host(address, _make_host("myhost")) is True
    assert _address_matches_host(address, _make_host("otherhost")) is False


def test_address_matches_host_by_provider() -> None:
    """An address with provider_name matches hosts with that provider."""
    address = AgentAddress(provider_name=ProviderInstanceName("modal"))

    assert _address_matches_host(address, _make_host(provider="modal")) is True
    assert _address_matches_host(address, _make_host(provider="docker")) is False


def test_address_matches_host_by_name_and_provider() -> None:
    """An address with both host_name and provider_name requires both to match."""
    address = AgentAddress(host_name=HostName("myhost"), provider_name=ProviderInstanceName("modal"))

    assert _address_matches_host(address, _make_host("myhost", "modal")) is True
    assert _address_matches_host(address, _make_host("myhost", "docker")) is False
    assert _address_matches_host(address, _make_host("other", "modal")) is False


# =============================================================================
# _address_matches_agent_match tests
# =============================================================================


def _make_match(
    name: str = "my-agent",
    host_name: str = "myhost",
    provider: str = "local",
) -> AgentMatch:
    return AgentMatch(
        agent_id=AgentId.generate(),
        agent_name=AgentName(name),
        host_id=HostId.generate(),
        host_name=HostName(host_name),
        provider_name=ProviderInstanceName(provider),
    )


def test_address_matches_agent_match_no_constraints() -> None:
    """An address with no host component matches any agent match."""
    address = AgentAddress()
    assert _address_matches_agent_match(address, _make_match()) is True


def test_address_matches_agent_match_by_host_name() -> None:
    """An address with host_name filters by host_name."""
    address = AgentAddress(host_name=HostName("myhost"))

    assert _address_matches_agent_match(address, _make_match(host_name="myhost")) is True
    assert _address_matches_agent_match(address, _make_match(host_name="other")) is False


def test_address_matches_agent_match_by_provider() -> None:
    """An address with provider_name filters by provider."""
    address = AgentAddress(provider_name=ProviderInstanceName("modal"))

    assert _address_matches_agent_match(address, _make_match(provider="modal")) is True
    assert _address_matches_agent_match(address, _make_match(provider="local")) is False


# =============================================================================
# filter_agents_by_host_constraint tests
# =============================================================================


def test_filter_agents_no_constraint() -> None:
    """When address has no host component, return all agents."""
    host = _make_host("h1", "local")
    agents: list[DiscoveredAgent] = []
    agents_by_host = {host: agents}

    result = filter_agents_by_host_constraint(agents_by_host, AgentAddress())
    assert len(result) == 1


def test_filter_agents_by_host_name() -> None:
    """Filter keeps only hosts matching the address host_name."""
    host1 = _make_host("h1", "local")
    host2 = _make_host("h2", "local")
    agents_by_host: dict[DiscoveredHost, list[DiscoveredAgent]] = {host1: [], host2: []}

    address = AgentAddress(host_name=HostName("h1"))
    result = filter_agents_by_host_constraint(agents_by_host, address)
    assert len(result) == 1
    assert host1 in result


def test_filter_agents_by_provider() -> None:
    """Filter keeps only hosts matching the address provider_name."""
    host1 = _make_host("h1", "local")
    host2 = _make_host("h2", "modal")
    agents_by_host: dict[DiscoveredHost, list[DiscoveredAgent]] = {host1: [], host2: []}

    address = AgentAddress(provider_name=ProviderInstanceName("modal"))
    result = filter_agents_by_host_constraint(agents_by_host, address)
    assert len(result) == 1
    assert host2 in result
