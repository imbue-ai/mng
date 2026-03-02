import json
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from datetime import timedelta
from datetime import timezone
from io import StringIO
from pathlib import Path

from loguru import logger

from imbue.mng.api.list import AgentErrorInfo
from imbue.mng.api.list import ErrorInfo
from imbue.mng.api.list import HostErrorInfo
from imbue.mng.api.list import ListResult
from imbue.mng.api.list import ProviderErrorInfo
from imbue.mng.api.list import _agent_to_cel_context
from imbue.mng.api.list import _apply_cel_filters
from imbue.mng.api.list import _warn_on_duplicate_host_names
from imbue.mng.config.completion_writer import AGENT_COMPLETIONS_CACHE_FILENAME
from imbue.mng.config.completion_writer import write_agent_names_cache
from imbue.mng.interfaces.data_types import AgentInfo
from imbue.mng.interfaces.data_types import HostInfo
from imbue.mng.primitives import AgentId
from imbue.mng.primitives import AgentLifecycleState
from imbue.mng.primitives import AgentName
from imbue.mng.primitives import AgentReference
from imbue.mng.primitives import CommandString
from imbue.mng.primitives import HostId
from imbue.mng.primitives import HostName
from imbue.mng.primitives import HostReference
from imbue.mng.primitives import ProviderInstanceName
from imbue.mng.utils.cel_utils import compile_cel_filters

# =============================================================================
# Helpers
# =============================================================================


def _make_host_info() -> HostInfo:
    return HostInfo(
        id=HostId.generate(),
        name="test-host",
        provider_name=ProviderInstanceName("local"),
    )


def _make_agent_info(name: str, host_info: HostInfo) -> AgentInfo:
    return AgentInfo(
        id=AgentId.generate(),
        name=AgentName(name),
        type="claude",
        command=CommandString("sleep 100"),
        work_dir=Path("/work"),
        create_time=datetime.now(timezone.utc),
        start_on_boot=False,
        state=AgentLifecycleState.RUNNING,
        host=host_info,
    )


# =============================================================================
# Completion Cache Write Tests
# =============================================================================


def test_write_agent_names_cache_writes_sorted_names(
    temp_host_dir: Path,
) -> None:
    """write_agent_names_cache should write sorted agent names to the cache file."""
    write_agent_names_cache(temp_host_dir, ["beta-agent", "alpha-agent"])

    cache_path = temp_host_dir / AGENT_COMPLETIONS_CACHE_FILENAME
    assert cache_path.is_file()
    cache_data = json.loads(cache_path.read_text())
    assert cache_data["names"] == ["alpha-agent", "beta-agent"]
    assert "updated_at" in cache_data


def test_write_agent_names_cache_writes_empty_list_for_no_agents(
    temp_host_dir: Path,
) -> None:
    """write_agent_names_cache should write an empty names list when no agents."""
    write_agent_names_cache(temp_host_dir, [])

    cache_path = temp_host_dir / AGENT_COMPLETIONS_CACHE_FILENAME
    assert cache_path.is_file()
    cache_data = json.loads(cache_path.read_text())
    assert cache_data["names"] == []


def test_write_agent_names_cache_deduplicates_names(
    temp_host_dir: Path,
) -> None:
    """write_agent_names_cache should deduplicate agent names."""
    write_agent_names_cache(temp_host_dir, ["same-name", "same-name"])

    cache_path = temp_host_dir / AGENT_COMPLETIONS_CACHE_FILENAME
    cache_data = json.loads(cache_path.read_text())
    assert cache_data["names"] == ["same-name"]


# =============================================================================
# Duplicate Host Name Warning Tests
# =============================================================================


def _make_host_ref(
    host_name: str,
    provider_name: str = "modal",
) -> HostReference:
    return HostReference(
        host_id=HostId.generate(),
        host_name=HostName(host_name),
        provider_name=ProviderInstanceName(provider_name),
    )


def _make_agent_ref(host_id: HostId, provider_name: str = "modal") -> AgentReference:
    return AgentReference(
        host_id=host_id,
        agent_id=AgentId.generate(),
        agent_name=AgentName("test-agent"),
        provider_name=ProviderInstanceName(provider_name),
    )


@contextmanager
def _capture_loguru_warnings() -> Iterator[StringIO]:
    """Capture loguru WARNING-level output into a StringIO buffer."""
    log_output = StringIO()
    sink_id = logger.add(log_output, level="WARNING", format="{message}")
    try:
        yield log_output
    finally:
        logger.remove(sink_id)


def test_warn_on_duplicate_host_names_no_warning_for_unique_names() -> None:
    """_warn_on_duplicate_host_names should not warn when all host names are unique."""
    ref_alpha = _make_host_ref("host-alpha")
    ref_beta = _make_host_ref("host-beta")
    ref_gamma = _make_host_ref("host-gamma")
    agents_by_host = {
        ref_alpha: [_make_agent_ref(ref_alpha.host_id)],
        ref_beta: [_make_agent_ref(ref_beta.host_id)],
        ref_gamma: [_make_agent_ref(ref_gamma.host_id)],
    }

    with _capture_loguru_warnings() as log_output:
        _warn_on_duplicate_host_names(agents_by_host)

    assert "Duplicate host name" not in log_output.getvalue()


def test_warn_on_duplicate_host_names_warns_on_duplicate_within_same_provider() -> None:
    """_warn_on_duplicate_host_names should warn when the same name appears twice on the same provider."""
    ref_dup_1 = _make_host_ref("duplicated-name", "modal")
    ref_dup_2 = _make_host_ref("duplicated-name", "modal")
    ref_unique = _make_host_ref("unique-name", "modal")
    agents_by_host = {
        ref_dup_1: [_make_agent_ref(ref_dup_1.host_id)],
        ref_dup_2: [_make_agent_ref(ref_dup_2.host_id)],
        ref_unique: [_make_agent_ref(ref_unique.host_id)],
    }

    with _capture_loguru_warnings() as log_output:
        _warn_on_duplicate_host_names(agents_by_host)

    output = log_output.getvalue()
    assert "Duplicate host name" in output
    assert "duplicated-name" in output
    assert "modal" in output


def test_warn_on_duplicate_host_names_no_warning_for_same_name_on_different_providers() -> None:
    """_warn_on_duplicate_host_names should not warn when the same name exists on different providers."""
    ref_modal = _make_host_ref("shared-name", "modal")
    ref_docker = _make_host_ref("shared-name", "docker")
    agents_by_host = {
        ref_modal: [_make_agent_ref(ref_modal.host_id, "modal")],
        ref_docker: [_make_agent_ref(ref_docker.host_id, "docker")],
    }

    with _capture_loguru_warnings() as log_output:
        _warn_on_duplicate_host_names(agents_by_host)

    assert "Duplicate host name" not in log_output.getvalue()


def test_warn_on_duplicate_host_names_empty_input() -> None:
    """_warn_on_duplicate_host_names should not warn with an empty input."""
    with _capture_loguru_warnings() as log_output:
        _warn_on_duplicate_host_names({})

    assert "Duplicate host name" not in log_output.getvalue()


def test_warn_on_duplicate_host_names_no_warning_when_destroyed_host_shares_name() -> None:
    """_warn_on_duplicate_host_names should not warn when a destroyed host (no agents) shares a name with an active host."""
    ref_destroyed = _make_host_ref("reused-name", "modal")
    ref_active = _make_host_ref("reused-name", "modal")
    agents_by_host: dict[HostReference, list[AgentReference]] = {
        ref_destroyed: [],
        ref_active: [_make_agent_ref(ref_active.host_id)],
    }

    with _capture_loguru_warnings() as log_output:
        _warn_on_duplicate_host_names(agents_by_host)

    assert "Duplicate host name" not in log_output.getvalue()


# =============================================================================
# ErrorInfo Tests
# =============================================================================


def test_error_info_build_creates_correct_error_from_exception() -> None:
    """ErrorInfo.build() should capture the exception type and message."""
    exception = RuntimeError("something went wrong")
    error = ErrorInfo.build(exception)
    assert error.exception_type == "RuntimeError"
    assert error.message == "something went wrong"


def test_error_info_build_captures_custom_exception_type() -> None:
    """ErrorInfo.build() should capture custom exception class names."""
    exception = ValueError("bad value")
    error = ErrorInfo.build(exception)
    assert error.exception_type == "ValueError"
    assert error.message == "bad value"


# =============================================================================
# ProviderErrorInfo Tests
# =============================================================================


def test_provider_error_info_build_for_provider() -> None:
    """ProviderErrorInfo.build_for_provider() should include the provider name."""
    exception = ConnectionError("cannot connect")
    provider_name = ProviderInstanceName("my-provider")
    error = ProviderErrorInfo.build_for_provider(exception, provider_name)
    assert error.exception_type == "ConnectionError"
    assert error.message == "cannot connect"
    assert error.provider_name == provider_name


# =============================================================================
# HostErrorInfo Tests
# =============================================================================


def test_host_error_info_build_for_host() -> None:
    """HostErrorInfo.build_for_host() should include the host ID."""
    exception = TimeoutError("host unreachable")
    host_id = HostId.generate()
    error = HostErrorInfo.build_for_host(exception, host_id)
    assert error.exception_type == "TimeoutError"
    assert error.message == "host unreachable"
    assert error.host_id == host_id


# =============================================================================
# AgentErrorInfo Tests
# =============================================================================


def test_agent_error_info_build_for_agent() -> None:
    """AgentErrorInfo.build_for_agent() should include the agent ID."""
    exception = OSError("agent process died")
    agent_id = AgentId.generate()
    error = AgentErrorInfo.build_for_agent(exception, agent_id)
    assert error.exception_type == "OSError"
    assert error.message == "agent process died"
    assert error.agent_id == agent_id


# =============================================================================
# ListResult Tests
# =============================================================================


def test_list_result_initializes_with_empty_lists() -> None:
    """ListResult should initialize with empty agents and errors lists."""
    result = ListResult()
    assert result.agents == []
    assert result.errors == []


def test_list_result_allows_appending() -> None:
    """ListResult agents and errors lists should be mutable."""
    result = ListResult()
    host_info = _make_host_info()
    agent = _make_agent_info("test-agent", host_info)
    result.agents.append(agent)
    assert len(result.agents) == 1
    assert result.agents[0].name == AgentName("test-agent")

    error = ErrorInfo.build(RuntimeError("oops"))
    result.errors.append(error)
    assert len(result.errors) == 1


# =============================================================================
# _agent_to_cel_context Tests
# =============================================================================


def test_agent_to_cel_context_basic_fields() -> None:
    """_agent_to_cel_context should convert AgentInfo to a dict with basic fields."""
    host_info = _make_host_info()
    agent = _make_agent_info("my-agent", host_info)
    context = _agent_to_cel_context(agent)

    assert context["name"] == "my-agent"
    assert context["type"] == "claude"
    assert context["state"] == "RUNNING"
    assert context["command"] == "sleep 100"


def test_agent_to_cel_context_computes_age() -> None:
    """_agent_to_cel_context should compute 'age' from create_time."""
    host_info = _make_host_info()
    create_time = datetime.now(timezone.utc) - timedelta(hours=2)
    agent = AgentInfo(
        id=AgentId.generate(),
        name=AgentName("aging-agent"),
        type="claude",
        command=CommandString("sleep 100"),
        work_dir=Path("/work"),
        create_time=create_time,
        start_on_boot=False,
        state=AgentLifecycleState.RUNNING,
        host=host_info,
    )
    context = _agent_to_cel_context(agent)

    assert "age" in context
    # Age should be approximately 7200 seconds (2 hours), with some tolerance
    assert context["age"] > 7000
    assert context["age"] < 7400


def test_agent_to_cel_context_computes_runtime() -> None:
    """_agent_to_cel_context should set 'runtime' from runtime_seconds."""
    host_info = _make_host_info()
    agent = AgentInfo(
        id=AgentId.generate(),
        name=AgentName("running-agent"),
        type="claude",
        command=CommandString("sleep 100"),
        work_dir=Path("/work"),
        create_time=datetime.now(timezone.utc),
        start_on_boot=False,
        state=AgentLifecycleState.RUNNING,
        runtime_seconds=3600.0,
        host=host_info,
    )
    context = _agent_to_cel_context(agent)

    assert context["runtime"] == 3600.0


def test_agent_to_cel_context_computes_idle() -> None:
    """_agent_to_cel_context should compute 'idle' from activity times."""
    host_info = _make_host_info()
    activity_time = datetime.now(timezone.utc) - timedelta(minutes=5)
    agent = AgentInfo(
        id=AgentId.generate(),
        name=AgentName("idle-agent"),
        type="claude",
        command=CommandString("sleep 100"),
        work_dir=Path("/work"),
        create_time=datetime.now(timezone.utc),
        start_on_boot=False,
        state=AgentLifecycleState.RUNNING,
        user_activity_time=activity_time,
        host=host_info,
    )
    context = _agent_to_cel_context(agent)

    assert "idle" in context
    # Idle should be approximately 300 seconds (5 minutes)
    assert context["idle"] > 280
    assert context["idle"] < 320


def test_agent_to_cel_context_normalizes_host_provider() -> None:
    """_agent_to_cel_context should rename host.provider_name to host.provider."""
    host_info = HostInfo(
        id=HostId.generate(),
        name="test-host",
        provider_name=ProviderInstanceName("modal"),
    )
    agent = _make_agent_info("test-agent", host_info)
    context = _agent_to_cel_context(agent)

    assert "host" in context
    host = context["host"]
    assert "provider" in host
    assert "provider_name" not in host
    assert host["provider"] == "modal"


# =============================================================================
# _apply_cel_filters Tests
# =============================================================================


def test_apply_cel_filters_includes_matching_agent() -> None:
    """_apply_cel_filters should return True when agent matches include filter."""
    host_info = _make_host_info()
    agent = _make_agent_info("target-agent", host_info)
    include_filters, exclude_filters = compile_cel_filters(
        include_filters=('name == "target-agent"',),
        exclude_filters=(),
    )
    assert _apply_cel_filters(agent, include_filters, exclude_filters) is True


def test_apply_cel_filters_excludes_non_matching_agent() -> None:
    """_apply_cel_filters should return False when agent does not match include filter."""
    host_info = _make_host_info()
    agent = _make_agent_info("other-agent", host_info)
    include_filters, exclude_filters = compile_cel_filters(
        include_filters=('name == "target-agent"',),
        exclude_filters=(),
    )
    assert _apply_cel_filters(agent, include_filters, exclude_filters) is False


def test_apply_cel_filters_exclude_filter_removes_agent() -> None:
    """_apply_cel_filters should return False when agent matches exclude filter."""
    host_info = _make_host_info()
    agent = _make_agent_info("unwanted-agent", host_info)
    include_filters, exclude_filters = compile_cel_filters(
        include_filters=(),
        exclude_filters=('name == "unwanted-agent"',),
    )
    assert _apply_cel_filters(agent, include_filters, exclude_filters) is False


def test_apply_cel_filters_no_filters_includes_all() -> None:
    """_apply_cel_filters should return True when no filters are provided."""
    host_info = _make_host_info()
    agent = _make_agent_info("any-agent", host_info)
    assert _apply_cel_filters(agent, [], []) is True
