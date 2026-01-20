"""Tests for provider registry."""

import pytest

from imbue.mngr.config.provider_registry import DockerProviderConfig
from imbue.mngr.config.provider_registry import LocalProviderConfig
from imbue.mngr.config.provider_registry import ModalProviderConfig
from imbue.mngr.config.provider_registry import get_provider_config_class
from imbue.mngr.errors import ConfigParseError
from imbue.mngr.errors import UnknownBackendError
from imbue.mngr.primitives import ProviderBackendName

# =============================================================================
# Tests for get_provider_config_class
# =============================================================================


def test_get_provider_config_class_returns_local_config() -> None:
    """get_provider_config_class should return LocalProviderConfig for 'local'."""
    config_class = get_provider_config_class("local")
    assert config_class is LocalProviderConfig


def test_get_provider_config_class_returns_docker_config() -> None:
    """get_provider_config_class should return DockerProviderConfig for 'docker'."""
    config_class = get_provider_config_class("docker")
    assert config_class is DockerProviderConfig


def test_get_provider_config_class_returns_modal_config() -> None:
    """get_provider_config_class should return ModalProviderConfig for 'modal'."""
    config_class = get_provider_config_class("modal")
    assert config_class is ModalProviderConfig


def test_get_provider_config_class_raises_for_unknown_backend() -> None:
    """get_provider_config_class should raise UnknownBackendError for unknown backend."""
    with pytest.raises(UnknownBackendError, match="Unknown provider backend"):
        get_provider_config_class("nonexistent")


# =============================================================================
# Tests for LocalProviderConfig
# =============================================================================


def test_local_provider_config_default_backend() -> None:
    """LocalProviderConfig should have 'local' as default backend."""
    config = LocalProviderConfig()
    assert config.backend == ProviderBackendName("local")


def test_local_provider_config_merge_with_returns_override_backend() -> None:
    """LocalProviderConfig.merge_with should return override's backend."""
    base = LocalProviderConfig(backend=ProviderBackendName("local"))
    override = LocalProviderConfig(backend=ProviderBackendName("local"))
    merged = base.merge_with(override)
    assert merged.backend == ProviderBackendName("local")


def test_local_provider_config_merge_with_raises_for_different_type() -> None:
    """LocalProviderConfig.merge_with should raise for different config type."""
    base = LocalProviderConfig()
    override = DockerProviderConfig()
    with pytest.raises(ConfigParseError, match="Cannot merge LocalProviderConfig"):
        base.merge_with(override)


def test_local_provider_config_register_hook() -> None:
    """LocalProviderConfig.register_provider_config should return correct tuple."""
    result = LocalProviderConfig.register_provider_config()
    assert result == ("local", LocalProviderConfig)


# =============================================================================
# Tests for DockerProviderConfig
# =============================================================================


def test_docker_provider_config_default_values() -> None:
    """DockerProviderConfig should have correct default values."""
    config = DockerProviderConfig()
    assert config.backend == ProviderBackendName("docker")
    assert config.host == ""


def test_docker_provider_config_merge_with_overrides_host() -> None:
    """DockerProviderConfig.merge_with should override host."""
    base = DockerProviderConfig(host="ssh://base@server")
    override = DockerProviderConfig(host="ssh://override@server")
    merged = base.merge_with(override)
    assert isinstance(merged, DockerProviderConfig)
    assert merged.host == "ssh://override@server"


def test_docker_provider_config_merge_with_raises_for_different_type() -> None:
    """DockerProviderConfig.merge_with should raise for different config type."""
    base = DockerProviderConfig()
    override = LocalProviderConfig()
    with pytest.raises(ConfigParseError, match="Cannot merge DockerProviderConfig"):
        base.merge_with(override)


def test_docker_provider_config_register_hook() -> None:
    """DockerProviderConfig.register_provider_config should return correct tuple."""
    result = DockerProviderConfig.register_provider_config()
    assert result == ("docker", DockerProviderConfig)


# =============================================================================
# Tests for ModalProviderConfig
# =============================================================================


def test_modal_provider_config_default_values() -> None:
    """ModalProviderConfig should have correct default values."""
    config = ModalProviderConfig()
    assert config.backend == ProviderBackendName("modal")
    assert config.environment == "main"


def test_modal_provider_config_merge_with_overrides_environment() -> None:
    """ModalProviderConfig.merge_with should override environment."""
    base = ModalProviderConfig(environment="base")
    override = ModalProviderConfig(environment="override")
    merged = base.merge_with(override)
    assert isinstance(merged, ModalProviderConfig)
    assert merged.environment == "override"


def test_modal_provider_config_merge_with_raises_for_different_type() -> None:
    """ModalProviderConfig.merge_with should raise for different config type."""
    base = ModalProviderConfig()
    override = LocalProviderConfig()
    with pytest.raises(ConfigParseError, match="Cannot merge ModalProviderConfig"):
        base.merge_with(override)


def test_modal_provider_config_register_hook() -> None:
    """ModalProviderConfig.register_provider_config should return correct tuple."""
    result = ModalProviderConfig.register_provider_config()
    assert result == ("modal", ModalProviderConfig)
