"""Tests for API data types."""

from pathlib import Path

from imbue.mngr.api.data_types import SourceLocation
from imbue.mngr.primitives import AgentId
from imbue.mngr.primitives import AgentName


def test_source_location_is_from_agent_true_with_agent_id() -> None:
    """SourceLocation.is_from_agent should be True when agent_id is set."""
    loc = SourceLocation(agent_id=AgentId.generate())
    assert loc.is_from_agent is True


def test_source_location_is_from_agent_true_with_agent_name() -> None:
    """SourceLocation.is_from_agent should be True when agent_name is set."""
    loc = SourceLocation(agent_name=AgentName("test"))
    assert loc.is_from_agent is True


def test_source_location_is_from_agent_false_when_neither() -> None:
    """SourceLocation.is_from_agent should be False when neither ID nor name set."""
    loc = SourceLocation(path=Path("/test"))
    assert loc.is_from_agent is False


def test_source_location_is_from_agent_true_with_both() -> None:
    """SourceLocation.is_from_agent should be True when both ID and name set."""
    loc = SourceLocation(
        agent_id=AgentId.generate(),
        agent_name=AgentName("test"),
    )
    assert loc.is_from_agent is True
