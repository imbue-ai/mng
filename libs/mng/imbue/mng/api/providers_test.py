"""Unit tests for provider registry and configuration."""

import pluggy
import pytest

from imbue.mng.api.providers import get_all_provider_instances
from imbue.mng.api.providers import get_provider_instance
from imbue.mng.config.data_types import MngConfig
from imbue.mng.config.data_types import MngContext
from imbue.mng.errors import UnknownBackendError
from imbue.mng.primitives import LOCAL_PROVIDER_NAME
from imbue.mng.primitives import ProviderBackendName
from imbue.mng.primitives import ProviderInstanceName
from imbue.mng.providers.local.config import LocalProviderConfig
from imbue.mng.providers.local.instance import LocalProviderInstance
from imbue.mng.providers.registry import get_backend
from imbue.mng.providers.registry import list_backends


def test_local_backend_is_registered() -> None:
    """Test that the local backend is automatically registered."""
    backends = list_backends()
    assert "local" in backends


def test_get_local_backend(plugin_manager: pluggy.PluginManager) -> None:
    """Test getting the local backend."""
    backend_class = get_backend("local", plugin_manager)
    assert backend_class.get_name() == LOCAL_PROVIDER_NAME


def test_get_unknown_backend_raises(plugin_manager: pluggy.PluginManager) -> None:
    """Test that requesting an unknown backend raises an error."""
    with pytest.raises(UnknownBackendError) as exc_info:
        get_backend("nonexistent", plugin_manager)
    assert "nonexistent" in str(exc_info.value)


def test_get_local_provider_instance(temp_mng_ctx: MngContext) -> None:
    """Test getting a local provider instance."""
    provider = get_provider_instance(LOCAL_PROVIDER_NAME, temp_mng_ctx)
    assert isinstance(provider, LocalProviderInstance)
    assert provider.name == LOCAL_PROVIDER_NAME


def test_get_configured_provider_instance(temp_mng_ctx: MngContext, mng_test_prefix: str) -> None:
    """Test getting a configured provider instance."""
    custom_name = ProviderInstanceName("my-local")
    config = MngConfig(
        default_host_dir=temp_mng_ctx.config.default_host_dir,
        prefix=mng_test_prefix,
        providers={
            custom_name: LocalProviderConfig(
                backend=ProviderBackendName("local"),
            ),
        },
    )
    mng_ctx = MngContext(config=config, pm=temp_mng_ctx.pm, profile_dir=temp_mng_ctx.profile_dir)
    provider = get_provider_instance(custom_name, mng_ctx)
    assert isinstance(provider, LocalProviderInstance)
    assert provider.name == custom_name


def test_get_all_provider_instances_with_configured_providers(temp_mng_ctx: MngContext, mng_test_prefix: str) -> None:
    """Test get_all_provider_instances includes configured providers."""
    custom_name = ProviderInstanceName("my-custom-local")
    config = MngConfig(
        default_host_dir=temp_mng_ctx.config.default_host_dir,
        prefix=mng_test_prefix,
        providers={
            custom_name: LocalProviderConfig(
                backend=ProviderBackendName("local"),
            ),
        },
    )
    mng_ctx = MngContext(config=config, pm=temp_mng_ctx.pm, profile_dir=temp_mng_ctx.profile_dir)
    providers = get_all_provider_instances(mng_ctx)

    provider_names = [p.name for p in providers]
    assert custom_name in provider_names


def test_get_all_provider_instances_includes_default_backends(temp_mng_ctx: MngContext) -> None:
    """Test get_all_provider_instances includes default backends."""
    providers = get_all_provider_instances(temp_mng_ctx)

    provider_names = [str(p.name) for p in providers]
    assert "local" in provider_names


def test_get_all_provider_instances_excludes_disabled_providers(
    temp_mng_ctx: MngContext, mng_test_prefix: str
) -> None:
    """Test get_all_provider_instances excludes providers with is_enabled=False."""
    disabled_name = ProviderInstanceName("disabled-local")
    config = MngConfig(
        default_host_dir=temp_mng_ctx.config.default_host_dir,
        prefix=mng_test_prefix,
        providers={
            disabled_name: LocalProviderConfig(
                backend=ProviderBackendName("local"),
                is_enabled=False,
            ),
        },
    )
    mng_ctx = MngContext(config=config, pm=temp_mng_ctx.pm, profile_dir=temp_mng_ctx.profile_dir)
    providers = get_all_provider_instances(mng_ctx)

    provider_names = [p.name for p in providers]
    assert disabled_name not in provider_names


def test_get_all_provider_instances_filters_by_enabled_backends(
    temp_mng_ctx: MngContext, mng_test_prefix: str
) -> None:
    """Test get_all_provider_instances only includes backends in enabled_backends when set."""
    config = MngConfig(
        default_host_dir=temp_mng_ctx.config.default_host_dir,
        prefix=mng_test_prefix,
        enabled_backends=[ProviderBackendName("local")],
    )
    mng_ctx = MngContext(config=config, pm=temp_mng_ctx.pm, profile_dir=temp_mng_ctx.profile_dir)
    providers = get_all_provider_instances(mng_ctx)

    provider_names = [str(p.name) for p in providers]
    # local should be included
    assert "local" in provider_names
    # No other backends should be included (filtering works)
    assert len(providers) == 1


def test_get_all_provider_instances_empty_enabled_backends_allows_all(temp_mng_ctx: MngContext) -> None:
    """Test get_all_provider_instances allows all backends when enabled_backends is empty."""
    # temp_mng_ctx has empty enabled_backends by default
    assert temp_mng_ctx.config.enabled_backends == []
    providers = get_all_provider_instances(temp_mng_ctx)

    # Should have at least local backend
    provider_names = [str(p.name) for p in providers]
    assert "local" in provider_names


def test_get_all_provider_instances_filters_by_provider_names(temp_mng_ctx: MngContext) -> None:
    """Test get_all_provider_instances filters to only specified providers."""
    providers = get_all_provider_instances(temp_mng_ctx, provider_names=("local",))

    assert len(providers) == 1
    assert str(providers[0].name) == "local"


def test_get_all_provider_instances_provider_names_excludes_others(temp_mng_ctx: MngContext) -> None:
    """Test providers not in provider_names are excluded."""
    providers = get_all_provider_instances(temp_mng_ctx, provider_names=("nonexistent",))

    assert len(providers) == 0


def test_get_all_provider_instances_provider_names_with_configured_provider(
    temp_mng_ctx: MngContext, mng_test_prefix: str
) -> None:
    """Test provider_names filtering works with configured providers."""
    custom_name = ProviderInstanceName("my-filtered-local")
    config = MngConfig(
        default_host_dir=temp_mng_ctx.config.default_host_dir,
        prefix=mng_test_prefix,
        providers={
            custom_name: LocalProviderConfig(
                backend=ProviderBackendName("local"),
            ),
        },
    )
    mng_ctx = MngContext(config=config, pm=temp_mng_ctx.pm, profile_dir=temp_mng_ctx.profile_dir)

    # Filter to only the custom provider
    providers = get_all_provider_instances(mng_ctx, provider_names=("my-filtered-local",))

    assert len(providers) == 1
    assert providers[0].name == custom_name

    # Filter to only local (should not include custom)
    providers_local = get_all_provider_instances(mng_ctx, provider_names=("local",))

    provider_names = [str(p.name) for p in providers_local]
    assert "local" in provider_names
    assert "my-filtered-local" not in provider_names
