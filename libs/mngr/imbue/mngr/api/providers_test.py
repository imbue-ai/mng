"""Unit tests for provider registry and configuration."""

import pytest

from imbue.mngr.api.providers import get_all_provider_instances
from imbue.mngr.api.providers import get_provider_instance
from imbue.mngr.api.providers import get_selected_providers
from imbue.mngr.config.data_types import MngrConfig
from imbue.mngr.config.data_types import MngrContext
from imbue.mngr.errors import UnknownBackendError
from imbue.mngr.primitives import LOCAL_PROVIDER_NAME
from imbue.mngr.primitives import ProviderBackendName
from imbue.mngr.primitives import ProviderInstanceName
from imbue.mngr.providers.local.config import LocalProviderConfig
from imbue.mngr.providers.local.instance import LocalProviderInstance
from imbue.mngr.providers.registry import get_backend
from imbue.mngr.providers.registry import list_backends


def test_local_backend_is_registered() -> None:
    """Test that the local backend is automatically registered."""
    backends = list_backends()
    assert "local" in backends


def test_get_local_backend() -> None:
    """Test getting the local backend."""
    backend_class = get_backend("local")
    assert backend_class.get_name() == LOCAL_PROVIDER_NAME


def test_get_unknown_backend_raises() -> None:
    """Test that requesting an unknown backend raises an error."""
    with pytest.raises(UnknownBackendError) as exc_info:
        get_backend("nonexistent")
    assert "nonexistent" in str(exc_info.value)


def test_get_local_provider_instance(temp_mngr_ctx: MngrContext) -> None:
    """Test getting a local provider instance."""
    provider = get_provider_instance(LOCAL_PROVIDER_NAME, temp_mngr_ctx)
    assert isinstance(provider, LocalProviderInstance)
    assert provider.name == LOCAL_PROVIDER_NAME


def test_get_configured_provider_instance(temp_mngr_ctx: MngrContext, mngr_test_prefix: str) -> None:
    """Test getting a configured provider instance."""
    custom_name = ProviderInstanceName("my-local")
    config = MngrConfig(
        default_host_dir=temp_mngr_ctx.config.default_host_dir,
        prefix=mngr_test_prefix,
        providers={
            custom_name: LocalProviderConfig(
                backend=ProviderBackendName("local"),
            ),
        },
    )
    mngr_ctx = MngrContext(config=config, pm=temp_mngr_ctx.pm, profile_dir=temp_mngr_ctx.profile_dir)
    provider = get_provider_instance(custom_name, mngr_ctx)
    assert isinstance(provider, LocalProviderInstance)
    assert provider.name == custom_name


def test_get_all_provider_instances_with_configured_providers(
    temp_mngr_ctx: MngrContext, mngr_test_prefix: str
) -> None:
    """Test get_all_provider_instances includes configured providers."""
    custom_name = ProviderInstanceName("my-custom-local")
    config = MngrConfig(
        default_host_dir=temp_mngr_ctx.config.default_host_dir,
        prefix=mngr_test_prefix,
        providers={
            custom_name: LocalProviderConfig(
                backend=ProviderBackendName("local"),
            ),
        },
    )
    mngr_ctx = MngrContext(config=config, pm=temp_mngr_ctx.pm, profile_dir=temp_mngr_ctx.profile_dir)
    providers = get_all_provider_instances(mngr_ctx)

    provider_names = [p.name for p in providers]
    assert custom_name in provider_names


def test_get_all_provider_instances_includes_default_backends(temp_mngr_ctx: MngrContext) -> None:
    """Test get_all_provider_instances includes default backends."""
    providers = get_all_provider_instances(temp_mngr_ctx)

    provider_names = [str(p.name) for p in providers]
    assert "local" in provider_names


def test_get_all_provider_instances_excludes_disabled_providers(
    temp_mngr_ctx: MngrContext, mngr_test_prefix: str
) -> None:
    """Test get_all_provider_instances excludes providers with is_enabled=False."""
    disabled_name = ProviderInstanceName("disabled-local")
    config = MngrConfig(
        default_host_dir=temp_mngr_ctx.config.default_host_dir,
        prefix=mngr_test_prefix,
        providers={
            disabled_name: LocalProviderConfig(
                backend=ProviderBackendName("local"),
                is_enabled=False,
            ),
        },
    )
    mngr_ctx = MngrContext(config=config, pm=temp_mngr_ctx.pm, profile_dir=temp_mngr_ctx.profile_dir)
    providers = get_all_provider_instances(mngr_ctx)

    provider_names = [p.name for p in providers]
    assert disabled_name not in provider_names


def test_get_all_provider_instances_filters_by_enabled_backends(
    temp_mngr_ctx: MngrContext, mngr_test_prefix: str
) -> None:
    """Test get_all_provider_instances only includes backends in enabled_backends when set."""
    config = MngrConfig(
        default_host_dir=temp_mngr_ctx.config.default_host_dir,
        prefix=mngr_test_prefix,
        enabled_backends=[ProviderBackendName("local")],
    )
    mngr_ctx = MngrContext(config=config, pm=temp_mngr_ctx.pm, profile_dir=temp_mngr_ctx.profile_dir)
    providers = get_all_provider_instances(mngr_ctx)

    provider_names = [str(p.name) for p in providers]
    # local should be included
    assert "local" in provider_names
    # No other backends should be included (filtering works)
    assert len(providers) == 1


def test_get_all_provider_instances_empty_enabled_backends_allows_all(temp_mngr_ctx: MngrContext) -> None:
    """Test get_all_provider_instances allows all backends when enabled_backends is empty."""
    # temp_mngr_ctx has empty enabled_backends by default
    assert temp_mngr_ctx.config.enabled_backends == []
    providers = get_all_provider_instances(temp_mngr_ctx)

    # Should have at least local backend
    provider_names = [str(p.name) for p in providers]
    assert "local" in provider_names


def test_get_all_provider_instances_filters_by_provider_names(temp_mngr_ctx: MngrContext) -> None:
    """Test get_all_provider_instances filters to only specified providers."""
    providers = get_all_provider_instances(temp_mngr_ctx, provider_names=("local",))

    assert len(providers) == 1
    assert str(providers[0].name) == "local"


def test_get_all_provider_instances_provider_names_excludes_others(temp_mngr_ctx: MngrContext) -> None:
    """Test providers not in provider_names are excluded."""
    providers = get_all_provider_instances(temp_mngr_ctx, provider_names=("nonexistent",))

    assert len(providers) == 0


def test_get_all_provider_instances_provider_names_with_configured_provider(
    temp_mngr_ctx: MngrContext, mngr_test_prefix: str
) -> None:
    """Test provider_names filtering works with configured providers."""
    custom_name = ProviderInstanceName("my-filtered-local")
    config = MngrConfig(
        default_host_dir=temp_mngr_ctx.config.default_host_dir,
        prefix=mngr_test_prefix,
        providers={
            custom_name: LocalProviderConfig(
                backend=ProviderBackendName("local"),
            ),
        },
    )
    mngr_ctx = MngrContext(config=config, pm=temp_mngr_ctx.pm, profile_dir=temp_mngr_ctx.profile_dir)

    # Filter to only the custom provider
    providers = get_all_provider_instances(mngr_ctx, provider_names=("my-filtered-local",))

    assert len(providers) == 1
    assert providers[0].name == custom_name

    # Filter to only local (should not include custom)
    providers_local = get_all_provider_instances(mngr_ctx, provider_names=("local",))

    provider_names = [str(p.name) for p in providers_local]
    assert "local" in provider_names
    assert "my-filtered-local" not in provider_names


def test_get_selected_providers_returns_all_when_all_providers_flag(temp_mngr_ctx: MngrContext) -> None:
    """get_selected_providers should return all providers when is_all_providers is True."""
    providers = get_selected_providers(
        mngr_ctx=temp_mngr_ctx,
        is_all_providers=True,
        provider_names=(),
    )

    provider_names = [str(p.name) for p in providers]
    assert "local" in provider_names


def test_get_selected_providers_returns_named_providers(temp_mngr_ctx: MngrContext) -> None:
    """get_selected_providers should return only named providers when names are given."""
    providers = get_selected_providers(
        mngr_ctx=temp_mngr_ctx,
        is_all_providers=False,
        provider_names=("local",),
    )

    assert len(providers) == 1
    assert str(providers[0].name) == "local"


def test_get_selected_providers_returns_all_when_no_names_and_not_all(temp_mngr_ctx: MngrContext) -> None:
    """get_selected_providers should return all providers when no names given and not all_providers."""
    providers = get_selected_providers(
        mngr_ctx=temp_mngr_ctx,
        is_all_providers=False,
        provider_names=(),
    )

    provider_names = [str(p.name) for p in providers]
    assert "local" in provider_names
