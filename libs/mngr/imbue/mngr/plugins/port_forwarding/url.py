import re

from imbue.imbue_common.primitives import PositiveInt
from imbue.imbue_common.pure import pure
from imbue.mngr.plugins.port_forwarding.data_types import DEFAULT_DOMAIN_SUFFIX
from imbue.mngr.plugins.port_forwarding.data_types import DEFAULT_VHOST_HTTP_PORT
from imbue.mngr.plugins.port_forwarding.data_types import ForwardedService
from imbue.mngr.plugins.port_forwarding.data_types import ForwardedServiceName


@pure
def sanitize_name_for_subdomain(name: str) -> str:
    """Convert a name to a valid DNS subdomain label.

    Lowercases, replaces underscores and dots with hyphens, strips leading/trailing
    hyphens, and collapses consecutive hyphens.
    """
    label = name.lower()
    label = label.replace("_", "-").replace(".", "-")
    label = re.sub(r"-+", "-", label)
    label = label.strip("-")
    if not label:
        label = "unnamed"
    return label


@pure
def compute_subdomain(
    service_name: str,
    agent_name: str,
    host_name: str,
) -> str:
    """Compute the full subdomain for a forwarded service."""
    service_label = sanitize_name_for_subdomain(service_name)
    agent_label = sanitize_name_for_subdomain(agent_name)
    host_label = sanitize_name_for_subdomain(host_name)
    return f"{service_label}.{agent_label}.{host_label}"


@pure
def compute_service_url(
    service_name: str,
    agent_name: str,
    host_name: str,
    domain_suffix: str = DEFAULT_DOMAIN_SUFFIX,
    vhost_port: int = DEFAULT_VHOST_HTTP_PORT,
) -> str:
    """Compute the full URL for a forwarded service."""
    subdomain = compute_subdomain(
        service_name=service_name,
        agent_name=agent_name,
        host_name=host_name,
    )
    return f"http://{subdomain}.{domain_suffix}:{vhost_port}"


@pure
def build_forwarded_service(
    service_name: str,
    local_port: int,
    agent_name: str,
    host_name: str,
    domain_suffix: str = DEFAULT_DOMAIN_SUFFIX,
    vhost_port: int = DEFAULT_VHOST_HTTP_PORT,
) -> ForwardedService:
    """Build a ForwardedService with computed subdomain and URL."""
    subdomain = compute_subdomain(
        service_name=service_name,
        agent_name=agent_name,
        host_name=host_name,
    )
    url = f"http://{subdomain}.{domain_suffix}:{vhost_port}"
    return ForwardedService(
        service_name=ForwardedServiceName(service_name),
        local_port=PositiveInt(local_port),
        agent_name=agent_name,
        host_name=host_name,
        subdomain=subdomain,
        url=url,
    )
