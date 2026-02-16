import pytest
from inline_snapshot import snapshot

from imbue.mngr.api.logs import LogsTarget
from imbue.mngr.api.logs import _extract_filename
from imbue.mngr.api.logs import _find_agent_in_hosts
from imbue.mngr.api.logs import _find_host_in_hosts
from imbue.mngr.api.logs import apply_head_or_tail
from imbue.mngr.api.logs import list_log_files
from imbue.mngr.api.logs import read_log_content
from imbue.mngr.errors import UserInputError
from imbue.mngr.primitives import AgentId
from imbue.mngr.primitives import AgentName
from imbue.mngr.primitives import AgentReference
from imbue.mngr.primitives import HostId
from imbue.mngr.primitives import HostName
from imbue.mngr.primitives import HostReference
from imbue.mngr.primitives import ProviderInstanceName
from imbue.mngr.providers.local.volume import LocalVolume


def _make_host_ref(
    host_id: HostId | None = None,
    host_name: str = "test-host",
) -> HostReference:
    return HostReference(
        host_id=host_id or HostId.generate(),
        host_name=HostName(host_name),
        provider_name=ProviderInstanceName("local"),
    )


def _make_agent_ref(
    agent_id: AgentId | None = None,
    agent_name: str = "test-agent",
) -> AgentReference:
    return AgentReference(
        host_id=HostId.generate(),
        agent_id=agent_id or AgentId.generate(),
        agent_name=AgentName(agent_name),
        provider_name=ProviderInstanceName("local"),
    )


def test_apply_head_or_tail_returns_all_when_no_filter() -> None:
    content = "line1\nline2\nline3\n"
    result = apply_head_or_tail(content, head_count=None, tail_count=None)
    assert result == content


def test_apply_head_or_tail_returns_first_n_lines() -> None:
    content = "line1\nline2\nline3\nline4\n"
    result = apply_head_or_tail(content, head_count=2, tail_count=None)
    assert result == snapshot("line1\nline2\n")


def test_apply_head_or_tail_returns_last_n_lines() -> None:
    content = "line1\nline2\nline3\nline4\n"
    result = apply_head_or_tail(content, head_count=None, tail_count=2)
    assert result == snapshot("line3\nline4\n")


def test_apply_head_or_tail_handles_head_larger_than_content() -> None:
    content = "line1\nline2\n"
    result = apply_head_or_tail(content, head_count=10, tail_count=None)
    assert result == content


def test_apply_head_or_tail_handles_tail_larger_than_content() -> None:
    content = "line1\nline2\n"
    result = apply_head_or_tail(content, head_count=None, tail_count=10)
    assert result == content


def test_apply_head_or_tail_handles_empty_content() -> None:
    result = apply_head_or_tail("", head_count=5, tail_count=None)
    assert result == ""


def test_extract_filename_from_simple_path() -> None:
    assert _extract_filename("output.log") == "output.log"


def test_extract_filename_from_nested_path() -> None:
    assert _extract_filename("some/dir/output.log") == "output.log"


def test_find_agent_in_hosts_by_name() -> None:
    agent_ref = _make_agent_ref(agent_name="my-agent")
    host_ref = _make_host_ref()
    agents_by_host = {host_ref: [agent_ref]}

    result = _find_agent_in_hosts("my-agent", agents_by_host)

    assert result is not None
    assert result[1].agent_name == AgentName("my-agent")


def test_find_agent_in_hosts_by_id() -> None:
    agent_id = AgentId.generate()
    agent_ref = _make_agent_ref(agent_id=agent_id, agent_name="some-agent")
    host_ref = _make_host_ref()
    agents_by_host = {host_ref: [agent_ref]}

    result = _find_agent_in_hosts(str(agent_id), agents_by_host)

    assert result is not None
    assert result[1].agent_id == agent_id


def test_find_agent_in_hosts_returns_none_when_not_found() -> None:
    host_ref = _make_host_ref()
    agents_by_host: dict[HostReference, list[AgentReference]] = {host_ref: []}

    result = _find_agent_in_hosts("nonexistent", agents_by_host)

    assert result is None


def test_find_agent_in_hosts_raises_on_duplicate_names() -> None:
    agent_ref_1 = _make_agent_ref(agent_name="duplicate")
    agent_ref_2 = _make_agent_ref(agent_name="duplicate")
    host_ref_1 = _make_host_ref(host_name="host-1")
    host_ref_2 = _make_host_ref(host_name="host-2")
    agents_by_host = {host_ref_1: [agent_ref_1], host_ref_2: [agent_ref_2]}

    with pytest.raises(UserInputError, match="Multiple agents"):
        _find_agent_in_hosts("duplicate", agents_by_host)


def test_find_host_in_hosts_by_name() -> None:
    host_ref = _make_host_ref(host_name="my-host")
    agents_by_host: dict[HostReference, list[AgentReference]] = {host_ref: []}

    result = _find_host_in_hosts("my-host", agents_by_host)

    assert result is not None
    assert result.host_name == HostName("my-host")


def test_find_host_in_hosts_by_id() -> None:
    host_id = HostId.generate()
    host_ref = _make_host_ref(host_id=host_id)
    agents_by_host: dict[HostReference, list[AgentReference]] = {host_ref: []}

    result = _find_host_in_hosts(str(host_id), agents_by_host)

    assert result is not None
    assert result.host_id == host_id


def test_find_host_in_hosts_returns_none_when_not_found() -> None:
    host_ref = _make_host_ref(host_name="other-host")
    agents_by_host: dict[HostReference, list[AgentReference]] = {host_ref: []}

    result = _find_host_in_hosts("nonexistent", agents_by_host)

    assert result is None


def test_find_host_in_hosts_raises_on_duplicate_names() -> None:
    host_ref_1 = _make_host_ref(host_name="duplicate-host")
    host_ref_2 = _make_host_ref(host_name="duplicate-host")
    agents_by_host: dict[HostReference, list[AgentReference]] = {host_ref_1: [], host_ref_2: []}

    with pytest.raises(UserInputError, match="Multiple hosts"):
        _find_host_in_hosts("duplicate-host", agents_by_host)


def test_list_log_files_returns_only_files(tmp_path) -> None:
    # Create a volume with files and directories
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()
    (logs_dir / "output.log").write_text("some log data")
    (logs_dir / "error.log").write_text("some errors")
    (logs_dir / "subdir").mkdir()

    volume = LocalVolume(root_path=logs_dir)
    target = LogsTarget(volume=volume, display_name="test agent")

    log_files = list_log_files(target)

    names = sorted(lf.name for lf in log_files)
    assert names == snapshot(["error.log", "output.log"])


def test_read_log_content_returns_file_contents(tmp_path) -> None:
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()
    (logs_dir / "test.log").write_text("hello world\nsecond line\n")

    volume = LocalVolume(root_path=logs_dir)
    target = LogsTarget(volume=volume, display_name="test agent")

    content = read_log_content(target, "test.log")

    assert content == snapshot("hello world\nsecond line\n")
