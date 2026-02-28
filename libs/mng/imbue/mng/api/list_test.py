from collections.abc import Iterator
from contextlib import contextmanager
from io import StringIO

from loguru import logger

from imbue.mng.api.list import _warn_on_duplicate_host_names
from imbue.mng.primitives import AgentId
from imbue.mng.primitives import AgentName
from imbue.mng.primitives import AgentReference
from imbue.mng.primitives import HostId
from imbue.mng.primitives import HostName
from imbue.mng.primitives import HostReference
from imbue.mng.primitives import ProviderInstanceName

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
