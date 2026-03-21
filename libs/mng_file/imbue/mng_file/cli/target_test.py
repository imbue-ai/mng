from pathlib import Path

import pytest

from imbue.mng.errors import MngError
from imbue.mng.errors import UserInputError
from imbue.mng.primitives import AgentId
from imbue.mng_file.cli.target import ResolveFileTargetResult
from imbue.mng_file.cli.target import _compute_agent_base_path
from imbue.mng_file.cli.target import _is_not_found_error
from imbue.mng_file.cli.target import _is_volume_accessible_path
from imbue.mng_file.cli.target import compute_volume_path
from imbue.mng_file.cli.target import resolve_full_path
from imbue.mng_file.data_types import PathRelativeTo


def test_resolve_full_path_with_relative_path() -> None:
    base = Path("/home/user/work")
    result = resolve_full_path(base, "config.toml")
    assert result == Path("/home/user/work/config.toml")


def test_resolve_full_path_with_nested_relative_path() -> None:
    base = Path("/home/user/work")
    result = resolve_full_path(base, "subdir/file.txt")
    assert result == Path("/home/user/work/subdir/file.txt")


def test_resolve_full_path_with_absolute_path_ignores_base() -> None:
    base = Path("/home/user/work")
    result = resolve_full_path(base, "/etc/hostname")
    assert result == Path("/etc/hostname")


def test_resolve_full_path_with_dot_relative_path() -> None:
    base = Path("/home/user/work")
    result = resolve_full_path(base, "./local/file.txt")
    assert result == Path("/home/user/work/local/file.txt")


def test_compute_agent_base_path_work() -> None:
    work_dir = Path("/agent/work")
    host_dir = Path("/home/user/.mng")
    agent_id = AgentId.generate()

    result = _compute_agent_base_path(
        relative_to=PathRelativeTo.WORK,
        work_dir=work_dir,
        host_dir=host_dir,
        agent_id=agent_id,
    )
    assert result == work_dir


def test_compute_agent_base_path_state() -> None:
    work_dir = Path("/agent/work")
    host_dir = Path("/home/user/.mng")
    agent_id = AgentId.generate()

    result = _compute_agent_base_path(
        relative_to=PathRelativeTo.STATE,
        work_dir=work_dir,
        host_dir=host_dir,
        agent_id=agent_id,
    )
    assert result == host_dir / "agents" / str(agent_id)


def test_compute_agent_base_path_host() -> None:
    work_dir = Path("/agent/work")
    host_dir = Path("/home/user/.mng")
    agent_id = AgentId.generate()

    result = _compute_agent_base_path(
        relative_to=PathRelativeTo.HOST,
        work_dir=work_dir,
        host_dir=host_dir,
        agent_id=agent_id,
    )
    assert result == host_dir


def test_is_volume_accessible_path_work_returns_false() -> None:
    assert _is_volume_accessible_path(PathRelativeTo.WORK) is False


def test_is_volume_accessible_path_state_returns_true() -> None:
    assert _is_volume_accessible_path(PathRelativeTo.STATE) is True


def test_is_volume_accessible_path_host_returns_true() -> None:
    assert _is_volume_accessible_path(PathRelativeTo.HOST) is True


def test_compute_volume_path_host_with_user_path() -> None:
    result = compute_volume_path(PathRelativeTo.HOST, agent_id=None, user_path="events/logs/events.jsonl")
    assert result == "events/logs/events.jsonl"


def test_compute_volume_path_host_without_user_path() -> None:
    result = compute_volume_path(PathRelativeTo.HOST, agent_id=None, user_path=None)
    assert result == "."


def test_compute_volume_path_state_with_user_path() -> None:
    agent_id = AgentId.generate()
    result = compute_volume_path(PathRelativeTo.STATE, agent_id=agent_id, user_path="events/logs/events.jsonl")
    assert result == f"agents/{agent_id}/events/logs/events.jsonl"


def test_compute_volume_path_state_without_user_path() -> None:
    agent_id = AgentId.generate()
    result = compute_volume_path(PathRelativeTo.STATE, agent_id=agent_id, user_path=None)
    assert result == f"agents/{agent_id}"


def test_compute_volume_path_state_without_agent_id_raises() -> None:
    with pytest.raises(UserInputError, match="requires an agent target"):
        compute_volume_path(PathRelativeTo.STATE, agent_id=None, user_path="file.txt")


def test_compute_volume_path_work_raises() -> None:
    agent_id = AgentId.generate()
    with pytest.raises(UserInputError, match="offline"):
        compute_volume_path(PathRelativeTo.WORK, agent_id=agent_id, user_path="file.txt")


def test_resolve_file_target_result_host_raises_when_offline() -> None:
    result = ResolveFileTargetResult(
        online_host=None,
        volume=None,
        base_path=Path("/test"),
        is_agent=False,
        agent_id=None,
        relative_to=PathRelativeTo.HOST,
    )
    with pytest.raises(MngError, match="offline"):
        _ = result.host


def test_resolve_file_target_result_is_online_false_when_no_host() -> None:
    result = ResolveFileTargetResult(
        online_host=None,
        volume=None,
        base_path=Path("/test"),
        is_agent=False,
        agent_id=None,
        relative_to=PathRelativeTo.HOST,
    )
    assert result.is_online is False


def test_is_not_found_error_returns_true_for_not_found() -> None:
    err = UserInputError("Could not find agent with ID or name: foo")
    assert _is_not_found_error(err) is True


def test_is_not_found_error_returns_false_for_multiple_match() -> None:
    err = UserInputError("Multiple agents found with ID or name: foo")
    assert _is_not_found_error(err) is False


def test_is_not_found_error_returns_false_for_other_error() -> None:
    err = UserInputError("Something completely different")
    assert _is_not_found_error(err) is False
