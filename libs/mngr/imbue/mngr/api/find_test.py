from pathlib import Path

import pytest

from imbue.mngr.api.find import ParsedSourceLocation
from imbue.mngr.api.find import determine_resolved_path
from imbue.mngr.api.find import get_host_from_list_by_id
from imbue.mngr.api.find import get_unique_host_from_list_by_name
from imbue.mngr.api.find import parse_source_string
from imbue.mngr.api.find import resolve_agent_reference
from imbue.mngr.api.find import resolve_host_reference
from imbue.mngr.errors import UserInputError
from imbue.mngr.primitives import AgentId
from imbue.mngr.primitives import AgentName
from imbue.mngr.primitives import AgentReference
from imbue.mngr.primitives import HostId
from imbue.mngr.primitives import HostName
from imbue.mngr.primitives import HostReference
from imbue.mngr.primitives import ProviderInstanceName


def test_parse_source_string_with_agent_only() -> None:
    parsed = parse_source_string(
        source="my-agent",
    )

    assert parsed == ParsedSourceLocation(
        agent="my-agent",
        host=None,
        path=None,
    )


def test_parse_source_string_with_agent_and_host() -> None:
    parsed = parse_source_string(
        source="my-agent.my-host",
    )

    assert parsed == ParsedSourceLocation(
        agent="my-agent",
        host="my-host",
        path=None,
    )


def test_parse_source_string_with_agent_host_and_path() -> None:
    parsed = parse_source_string(
        source="my-agent.my-host:/path/to/dir",
    )

    assert parsed == ParsedSourceLocation(
        agent="my-agent",
        host="my-host",
        path="/path/to/dir",
    )


def test_parse_source_string_with_host_and_path() -> None:
    parsed = parse_source_string(
        source="my-host:/path/to/dir",
    )

    assert parsed == ParsedSourceLocation(
        agent=None,
        host="my-host",
        path="/path/to/dir",
    )


def test_parse_source_string_with_absolute_path() -> None:
    parsed = parse_source_string(
        source="/path/to/dir",
    )

    assert parsed == ParsedSourceLocation(
        agent=None,
        host=None,
        path="/path/to/dir",
    )


def test_parse_source_string_with_relative_path() -> None:
    parsed = parse_source_string(
        source="./path/to/dir",
    )

    assert parsed == ParsedSourceLocation(
        agent=None,
        host=None,
        path="./path/to/dir",
    )


def test_parse_source_string_with_home_path() -> None:
    parsed = parse_source_string(
        source="~/path/to/dir",
    )

    assert parsed == ParsedSourceLocation(
        agent=None,
        host=None,
        path="~/path/to/dir",
    )


def test_parse_source_string_with_parent_path() -> None:
    parsed = parse_source_string(
        source="../path/to/dir",
    )

    assert parsed == ParsedSourceLocation(
        agent=None,
        host=None,
        path="../path/to/dir",
    )


def test_parse_source_string_with_individual_parameters() -> None:
    parsed = parse_source_string(
        source=None,
        source_agent="my-agent",
        source_host="my-host",
        source_path="/path/to/dir",
    )

    assert parsed == ParsedSourceLocation(
        agent="my-agent",
        host="my-host",
        path="/path/to/dir",
    )


def test_parse_source_string_with_all_none() -> None:
    parsed = parse_source_string(
        source=None,
    )

    assert parsed == ParsedSourceLocation(
        agent=None,
        host=None,
        path=None,
    )


def test_parse_source_string_raises_when_both_source_and_individual_params() -> None:
    with pytest.raises(UserInputError, match="Specify either --source or the individual source parameters"):
        parse_source_string(
            source="my-agent",
            source_agent="another-agent",
            source_host=None,
            source_path=None,
        )


def test_resolve_host_reference_with_none() -> None:
    result = resolve_host_reference(
        host_identifier=None,
        all_hosts=[],
    )

    assert result is None


def test_resolve_host_reference_by_id() -> None:
    host_id = HostId.generate()
    host_ref = HostReference(
        host_id=host_id,
        host_name=HostName("test-host"),
        provider_name=ProviderInstanceName("local"),
    )

    result = resolve_host_reference(
        host_identifier=str(host_id),
        all_hosts=[host_ref],
    )

    assert result == host_ref


def test_resolve_host_reference_by_name() -> None:
    host_ref = HostReference(
        host_id=HostId.generate(),
        host_name=HostName("test-host"),
        provider_name=ProviderInstanceName("local"),
    )

    result = resolve_host_reference(
        host_identifier="test-host",
        all_hosts=[host_ref],
    )

    assert result == host_ref


def test_resolve_host_reference_raises_when_not_found() -> None:
    with pytest.raises(UserInputError, match="Could not find host with ID or name: nonexistent"):
        resolve_host_reference(
            host_identifier="nonexistent",
            all_hosts=[],
        )


def test_resolve_host_reference_raises_when_multiple_hosts_with_same_name() -> None:
    host_ref1 = HostReference(
        host_id=HostId.generate(),
        host_name=HostName("test-host"),
        provider_name=ProviderInstanceName("local"),
    )
    host_ref2 = HostReference(
        host_id=HostId.generate(),
        host_name=HostName("test-host"),
        provider_name=ProviderInstanceName("docker"),
    )

    with pytest.raises(UserInputError, match="Multiple hosts found with name: test-host"):
        resolve_host_reference(
            host_identifier="test-host",
            all_hosts=[host_ref1, host_ref2],
        )


def test_resolve_agent_reference_with_none() -> None:
    result = resolve_agent_reference(
        agent_identifier=None,
        resolved_host=None,
        agents_by_host={},
    )

    assert result is None


def test_resolve_agent_reference_by_id() -> None:
    host_id = HostId.generate()
    agent_id = AgentId.generate()
    host_ref = HostReference(
        host_id=host_id,
        host_name=HostName("test-host"),
        provider_name=ProviderInstanceName("local"),
    )
    agent_ref = AgentReference(
        host_id=host_id,
        agent_id=agent_id,
        agent_name=AgentName("test-agent"),
        provider_name=ProviderInstanceName("local"),
    )

    result = resolve_agent_reference(
        agent_identifier=str(agent_id),
        resolved_host=None,
        agents_by_host={host_ref: [agent_ref]},
    )

    assert result == (host_ref, agent_ref)


def test_resolve_agent_reference_by_name() -> None:
    host_id = HostId.generate()
    agent_id = AgentId.generate()
    host_ref = HostReference(
        host_id=host_id,
        host_name=HostName("test-host"),
        provider_name=ProviderInstanceName("local"),
    )
    agent_ref = AgentReference(
        host_id=host_id,
        agent_id=agent_id,
        agent_name=AgentName("test-agent"),
        provider_name=ProviderInstanceName("local"),
    )

    result = resolve_agent_reference(
        agent_identifier="test-agent",
        resolved_host=None,
        agents_by_host={host_ref: [agent_ref]},
    )

    assert result == (host_ref, agent_ref)


def test_resolve_agent_reference_with_resolved_host_filters_by_host() -> None:
    host_id1 = HostId.generate()
    host_id2 = HostId.generate()
    agent_id1 = AgentId.generate()
    agent_id2 = AgentId.generate()

    host_ref1 = HostReference(
        host_id=host_id1,
        host_name=HostName("host1"),
        provider_name=ProviderInstanceName("local"),
    )
    host_ref2 = HostReference(
        host_id=host_id2,
        host_name=HostName("host2"),
        provider_name=ProviderInstanceName("local"),
    )

    agent_ref1 = AgentReference(
        host_id=host_id1,
        agent_id=agent_id1,
        agent_name=AgentName("test-agent"),
        provider_name=ProviderInstanceName("local"),
    )
    agent_ref2 = AgentReference(
        host_id=host_id2,
        agent_id=agent_id2,
        agent_name=AgentName("test-agent"),
        provider_name=ProviderInstanceName("local"),
    )

    result = resolve_agent_reference(
        agent_identifier="test-agent",
        resolved_host=host_ref1,
        agents_by_host={
            host_ref1: [agent_ref1],
            host_ref2: [agent_ref2],
        },
    )

    assert result == (host_ref1, agent_ref1)


def test_resolve_agent_reference_raises_when_not_found() -> None:
    with pytest.raises(UserInputError, match="Could not find agent with ID or name: nonexistent"):
        resolve_agent_reference(
            agent_identifier="nonexistent",
            resolved_host=None,
            agents_by_host={},
        )


def test_resolve_agent_reference_raises_when_multiple_agents_match() -> None:
    host_id1 = HostId.generate()
    host_id2 = HostId.generate()
    agent_id1 = AgentId.generate()
    agent_id2 = AgentId.generate()

    host_ref1 = HostReference(
        host_id=host_id1,
        host_name=HostName("host1"),
        provider_name=ProviderInstanceName("local"),
    )
    host_ref2 = HostReference(
        host_id=host_id2,
        host_name=HostName("host2"),
        provider_name=ProviderInstanceName("local"),
    )

    agent_ref1 = AgentReference(
        host_id=host_id1,
        agent_id=agent_id1,
        agent_name=AgentName("test-agent"),
        provider_name=ProviderInstanceName("local"),
    )
    agent_ref2 = AgentReference(
        host_id=host_id2,
        agent_id=agent_id2,
        agent_name=AgentName("test-agent"),
        provider_name=ProviderInstanceName("local"),
    )

    with pytest.raises(UserInputError, match="Multiple agents found with ID or name: test-agent"):
        resolve_agent_reference(
            agent_identifier="test-agent",
            resolved_host=None,
            agents_by_host={
                host_ref1: [agent_ref1],
                host_ref2: [agent_ref2],
            },
        )


def test_parse_source_string_with_colons_in_path() -> None:
    parsed = parse_source_string(
        source="my-host:/path/with:colons:in:it.txt",
    )

    assert parsed == ParsedSourceLocation(
        agent=None,
        host="my-host",
        path="/path/with:colons:in:it.txt",
    )


def test_parse_source_string_with_agent_host_and_colons_in_path() -> None:
    parsed = parse_source_string(
        source="agent.host:/weird:path:file.txt",
    )

    assert parsed == ParsedSourceLocation(
        agent="agent",
        host="host",
        path="/weird:path:file.txt",
    )


def test_parse_source_string_with_empty_path_after_colon() -> None:
    parsed = parse_source_string(
        source="my-host:",
    )

    assert parsed == ParsedSourceLocation(
        agent=None,
        host="my-host",
        path="",
    )


def test_parse_source_string_with_url_as_path() -> None:
    parsed = parse_source_string(
        source="my-agent:http://example.com/path",
    )

    assert parsed == ParsedSourceLocation(
        agent=None,
        host="my-agent",
        path="http://example.com/path",
    )


def test_parse_source_string_with_agent_host_provider() -> None:
    parsed = parse_source_string(
        source="my-agent.my-host.docker",
    )

    assert parsed == ParsedSourceLocation(
        agent="my-agent",
        host="my-host.docker",
        path=None,
    )


def test_parse_source_string_with_agent_host_provider_and_path() -> None:
    parsed = parse_source_string(
        source="my-agent.my-host.modal:/path/to/dir",
    )

    assert parsed == ParsedSourceLocation(
        agent="my-agent",
        host="my-host.modal",
        path="/path/to/dir",
    )


def test_parse_source_string_with_host_provider_and_path_ambiguity() -> None:
    parsed = parse_source_string(
        source="my-host.docker:/path/to/dir",
    )

    assert parsed == ParsedSourceLocation(
        agent="my-host",
        host="docker",
        path="/path/to/dir",
    )


def test_parse_source_string_with_windows_drive_letter_ambiguity() -> None:
    parsed = parse_source_string(
        source="C:/Windows/path",
    )

    assert parsed == ParsedSourceLocation(
        agent=None,
        host="C",
        path="/Windows/path",
    )


def test_get_host_from_list_by_id_returns_matching_host() -> None:
    """get_host_from_list_by_id should return matching host."""
    host_id = HostId.generate()
    host_ref = HostReference(
        host_id=host_id,
        host_name=HostName("test"),
        provider_name=ProviderInstanceName("local"),
    )
    result = get_host_from_list_by_id(host_id, [host_ref])
    assert result == host_ref


def test_get_host_from_list_by_id_returns_none_when_not_found() -> None:
    """get_host_from_list_by_id should return None when not found."""
    result = get_host_from_list_by_id(HostId.generate(), [])
    assert result is None


def test_get_unique_host_from_list_by_name_returns_matching_host() -> None:
    """get_unique_host_from_list_by_name should return matching host."""
    host_name = HostName("test-host")
    host_ref = HostReference(
        host_id=HostId.generate(),
        host_name=host_name,
        provider_name=ProviderInstanceName("local"),
    )
    result = get_unique_host_from_list_by_name(host_name, [host_ref])
    assert result == host_ref


def test_get_unique_host_from_list_by_name_returns_none_when_empty() -> None:
    """get_unique_host_from_list_by_name should return None for empty list."""
    result = get_unique_host_from_list_by_name(HostName("test"), [])
    assert result is None


def test_determine_resolved_path_uses_parsed_path_when_available() -> None:
    """determine_resolved_path should prefer parsed_path when available."""
    result = determine_resolved_path(
        parsed_path="/explicit/path",
        resolved_agent=None,
        agent_work_dir_if_available=None,
    )
    assert result == Path("/explicit/path")


def test_determine_resolved_path_uses_agent_work_dir_when_no_parsed_path() -> None:
    """determine_resolved_path should use agent work dir when no parsed path."""
    agent_ref = AgentReference(
        host_id=HostId.generate(),
        agent_id=AgentId.generate(),
        agent_name=AgentName("test"),
        provider_name=ProviderInstanceName("local"),
    )
    result = determine_resolved_path(
        parsed_path=None,
        resolved_agent=agent_ref,
        agent_work_dir_if_available=Path("/agent/work/dir"),
    )
    assert result == Path("/agent/work/dir")


def test_determine_resolved_path_prefers_parsed_path_over_agent_work_dir() -> None:
    """determine_resolved_path should prefer parsed path even when agent work dir available."""
    agent_ref = AgentReference(
        host_id=HostId.generate(),
        agent_id=AgentId.generate(),
        agent_name=AgentName("test"),
        provider_name=ProviderInstanceName("local"),
    )
    result = determine_resolved_path(
        parsed_path="/explicit/path",
        resolved_agent=agent_ref,
        agent_work_dir_if_available=Path("/agent/work/dir"),
    )
    assert result == Path("/explicit/path")


def test_determine_resolved_path_raises_when_agent_but_no_work_dir() -> None:
    """determine_resolved_path should raise when agent specified but work dir not found."""
    agent_ref = AgentReference(
        host_id=HostId.generate(),
        agent_id=AgentId.generate(),
        agent_name=AgentName("test"),
        provider_name=ProviderInstanceName("local"),
    )
    with pytest.raises(UserInputError, match="Could not find agent"):
        determine_resolved_path(
            parsed_path=None,
            resolved_agent=agent_ref,
            agent_work_dir_if_available=None,
        )


def test_determine_resolved_path_raises_when_no_path_and_no_agent() -> None:
    """determine_resolved_path should raise when neither path nor agent specified."""
    with pytest.raises(UserInputError, match="Must specify a path"):
        determine_resolved_path(
            parsed_path=None,
            resolved_agent=None,
            agent_work_dir_if_available=None,
        )


def test_parse_source_string_with_empty_prefix_before_colon() -> None:
    """parse_source_string should handle :path format (empty prefix before colon)."""
    parsed = parse_source_string(source=":/path/to/dir")
    assert parsed == ParsedSourceLocation(
        agent=None,
        host=None,
        path="/path/to/dir",
    )
