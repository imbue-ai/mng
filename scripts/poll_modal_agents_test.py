import json

from scripts.poll_modal_agents import detect_state_transitions
from scripts.poll_modal_agents import parse_all_agents_from_jsonl


def test_parse_all_agents_from_jsonl_parses_single_agent() -> None:
    jsonl = json.dumps({"name": "my-agent", "id": "agent-123", "state": "RUNNING"})
    result = parse_all_agents_from_jsonl(jsonl)
    assert result == {"my-agent": "RUNNING"}


def test_parse_all_agents_from_jsonl_parses_multiple_agents() -> None:
    jsonl = (
        json.dumps({"name": "agent-a", "id": "id-a", "state": "RUNNING"})
        + "\n"
        + json.dumps({"name": "agent-b", "id": "id-b", "state": "WAITING"})
        + "\n"
        + json.dumps({"name": "agent-c", "id": "id-c", "state": "DONE"})
    )
    result = parse_all_agents_from_jsonl(jsonl)
    assert result == {
        "agent-a": "RUNNING",
        "agent-b": "WAITING",
        "agent-c": "DONE",
    }


def test_parse_all_agents_from_jsonl_returns_empty_dict_for_empty_input() -> None:
    result = parse_all_agents_from_jsonl("")
    assert result == {}


def test_parse_all_agents_from_jsonl_skips_malformed_lines() -> None:
    jsonl = "not json\n" + json.dumps({"name": "my-agent", "id": "agent-123", "state": "STOPPED"})
    result = parse_all_agents_from_jsonl(jsonl)
    assert result == {"my-agent": "STOPPED"}


def test_parse_all_agents_from_jsonl_skips_non_dict_lines() -> None:
    jsonl = json.dumps([1, 2, 3]) + "\n" + json.dumps({"name": "my-agent", "id": "id-1", "state": "REPLACED"})
    result = parse_all_agents_from_jsonl(jsonl)
    assert result == {"my-agent": "REPLACED"}


def test_parse_all_agents_from_jsonl_skips_lines_missing_name_or_state() -> None:
    jsonl = (
        json.dumps({"id": "id-1", "state": "RUNNING"})
        + "\n"
        + json.dumps({"name": "good-agent", "state": "WAITING"})
        + "\n"
        + json.dumps({"name": "no-state", "id": "id-2"})
    )
    result = parse_all_agents_from_jsonl(jsonl)
    assert result == {"good-agent": "WAITING"}


def test_detect_state_transitions_detects_running_to_waiting() -> None:
    previous = {"agent-a": "RUNNING"}
    current = {"agent-a": "WAITING"}
    transitions = detect_state_transitions(previous, current)
    assert transitions == [("agent-a", "RUNNING", "WAITING")]


def test_detect_state_transitions_detects_running_to_done() -> None:
    previous = {"agent-a": "RUNNING"}
    current = {"agent-a": "DONE"}
    transitions = detect_state_transitions(previous, current)
    assert transitions == [("agent-a", "RUNNING", "DONE")]


def test_detect_state_transitions_ignores_still_running() -> None:
    previous = {"agent-a": "RUNNING"}
    current = {"agent-a": "RUNNING"}
    transitions = detect_state_transitions(previous, current)
    assert transitions == []


def test_detect_state_transitions_ignores_non_running_changes() -> None:
    previous = {"agent-a": "WAITING", "agent-b": "STOPPED"}
    current = {"agent-a": "DONE", "agent-b": "RUNNING"}
    transitions = detect_state_transitions(previous, current)
    assert transitions == []


def test_detect_state_transitions_detects_disappeared_agent() -> None:
    previous = {"agent-a": "RUNNING"}
    current = {}
    transitions = detect_state_transitions(previous, current)
    assert transitions == [("agent-a", "RUNNING", "GONE")]


def test_detect_state_transitions_handles_multiple_transitions() -> None:
    previous = {"agent-a": "RUNNING", "agent-b": "RUNNING", "agent-c": "WAITING"}
    current = {"agent-a": "WAITING", "agent-b": "DONE", "agent-c": "DONE"}
    transitions = detect_state_transitions(previous, current)
    # Both running agents transitioned, but not agent-c (was WAITING)
    assert len(transitions) == 2
    names = {t[0] for t in transitions}
    assert names == {"agent-a", "agent-b"}


def test_detect_state_transitions_handles_empty_previous() -> None:
    previous: dict[str, str] = {}
    current = {"agent-a": "RUNNING"}
    transitions = detect_state_transitions(previous, current)
    assert transitions == []


def test_detect_state_transitions_handles_empty_both() -> None:
    transitions = detect_state_transitions({}, {})
    assert transitions == []
