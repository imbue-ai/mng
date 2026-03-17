import json

from imbue.minds.cli.update import _parse_agents_from_output


def test_parse_agents_from_output_extracts_records() -> None:
    """Verify _parse_agents_from_output extracts agent records from JSON."""
    json_str = json.dumps(
        {
            "agents": [
                {"id": "agent-abc123", "name": "selene", "work_dir": "/tmp/minds/selene"},
            ]
        }
    )
    agents = _parse_agents_from_output(json_str)
    assert len(agents) == 1
    assert agents[0]["id"] == "agent-abc123"
    assert agents[0]["name"] == "selene"


def test_parse_agents_from_output_handles_empty() -> None:
    """Verify _parse_agents_from_output returns empty list for no agents."""
    json_str = json.dumps({"agents": []})
    agents = _parse_agents_from_output(json_str)
    assert agents == []


def test_parse_agents_from_output_handles_non_json() -> None:
    """Verify _parse_agents_from_output handles non-JSON output gracefully."""
    agents = _parse_agents_from_output("not json at all")
    assert agents == []


def test_parse_agents_from_output_handles_mixed_output() -> None:
    """Verify _parse_agents_from_output handles SSH errors mixed with JSON."""
    output = "WARNING: some SSH error\n" + json.dumps({"agents": [{"id": "agent-xyz", "name": "test"}]})
    agents = _parse_agents_from_output(output)
    assert len(agents) == 1
    assert agents[0]["id"] == "agent-xyz"
