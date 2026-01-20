"""Tests for primitives."""

from imbue.mngr.primitives import HostName
from imbue.mngr.primitives import ProviderInstanceName


def test_host_name_extracts_provider_name_when_present() -> None:
    """HostName.provider_name should extract provider after dot."""
    host_name = HostName("myhost.docker")
    assert host_name.provider_name == ProviderInstanceName("docker")


def test_host_name_provider_name_is_none_when_no_dot() -> None:
    """HostName.provider_name should be None when no dot in name."""
    host_name = HostName("myhost")
    assert host_name.provider_name is None


def test_host_name_provider_name_returns_none_with_multiple_dots() -> None:
    """HostName.provider_name should return None when more than 2 parts."""
    host_name = HostName("my.host.docker")
    assert host_name.provider_name is None


def test_host_name_short_name_without_provider() -> None:
    """HostName.short_name should return full name when no provider."""
    host_name = HostName("myhost")
    assert host_name.short_name == "myhost"


def test_host_name_short_name_with_provider() -> None:
    """HostName.short_name should return name before dot."""
    host_name = HostName("myhost.docker")
    assert host_name.short_name == "myhost"
