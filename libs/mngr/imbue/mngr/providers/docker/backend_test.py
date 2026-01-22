"""Tests for the DockerProviderBackend."""

from pathlib import Path

import pluggy
import pytest

from imbue.mngr.config.data_types import MngrConfig
from imbue.mngr.config.data_types import MngrContext
from imbue.mngr.primitives import ProviderInstanceName
from imbue.mngr.providers.docker.backend import _get_or_create_user_id
from imbue.mngr.providers.docker.backend import DOCKER_BACKEND_NAME
from imbue.mngr.providers.docker.backend import DockerProviderBackend
from imbue.mngr.providers.docker.instance import DockerProviderInstance


def test_docker_backend_name() -> None:
    assert DockerProviderBackend.get_name() == DOCKER_BACKEND_NAME


def test_docker_backend_description() -> None:
    desc = DockerProviderBackend.get_description()
    assert "Docker" in desc


def test_docker_backend_build_args_help() -> None:
    help_text = DockerProviderBackend.get_build_args_help()
    assert "--cpu" in help_text
    assert "--memory" in help_text
    assert "--image" in help_text


def test_docker_backend_start_args_help() -> None:
    help_text = DockerProviderBackend.get_start_args_help()
    assert "No start arguments" in help_text


@pytest.fixture
def temp_mngr_ctx(tmp_path: Path) -> MngrContext:
    """Create a temporary MngrContext for testing."""
    config = MngrConfig(
        default_host_dir=tmp_path / "mngr",
        prefix="mngr-test-",
    )
    pm = pluggy.PluginManager("mngr")
    return MngrContext(config=config, pm=pm)


def test_get_or_create_user_id_creates_new(temp_mngr_ctx: MngrContext) -> None:
    """Test that _get_or_create_user_id creates a new user ID."""
    user_id = _get_or_create_user_id(temp_mngr_ctx)
    assert len(user_id) == 8
    assert user_id.isalnum()


def test_get_or_create_user_id_returns_existing(temp_mngr_ctx: MngrContext) -> None:
    """Test that _get_or_create_user_id returns existing user ID."""
    user_id1 = _get_or_create_user_id(temp_mngr_ctx)
    user_id2 = _get_or_create_user_id(temp_mngr_ctx)
    assert user_id1 == user_id2


def test_build_provider_instance(temp_mngr_ctx: MngrContext) -> None:
    """Test building a DockerProviderInstance."""
    instance = DockerProviderBackend.build_provider_instance(
        name=ProviderInstanceName("docker-test"),
        instance_configuration={},
        mngr_ctx=temp_mngr_ctx,
    )

    assert isinstance(instance, DockerProviderInstance)
    assert instance.name == ProviderInstanceName("docker-test")


def test_build_provider_instance_with_custom_config(temp_mngr_ctx: MngrContext) -> None:
    """Test building a DockerProviderInstance with custom configuration."""
    instance = DockerProviderBackend.build_provider_instance(
        name=ProviderInstanceName("docker-custom"),
        instance_configuration={
            "default_cpu": 2.0,
            "default_memory": 4.0,
            "host_dir": "/custom/path",
        },
        mngr_ctx=temp_mngr_ctx,
    )

    assert isinstance(instance, DockerProviderInstance)
    assert instance.default_cpu == 2.0
    assert instance.default_memory == 4.0
    assert instance.host_dir == Path("/custom/path")
