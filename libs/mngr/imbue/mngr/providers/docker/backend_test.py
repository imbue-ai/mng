from pathlib import Path

from imbue.mngr.config.data_types import MngrContext
from imbue.mngr.primitives import ProviderBackendName
from imbue.mngr.primitives import ProviderInstanceName
from imbue.mngr.providers.docker.backend import DOCKER_BACKEND_NAME
from imbue.mngr.providers.docker.backend import DockerProviderBackend
from imbue.mngr.providers.docker.config import DockerProviderConfig
from imbue.mngr.providers.docker.instance import DockerProviderInstance


def test_backend_name() -> None:
    assert DockerProviderBackend.get_name() == DOCKER_BACKEND_NAME
    assert DockerProviderBackend.get_name() == ProviderBackendName("docker")


def test_backend_description() -> None:
    desc = DockerProviderBackend.get_description()
    assert isinstance(desc, str)
    assert len(desc) > 0
    assert "docker" in desc.lower()


def test_backend_build_args_help() -> None:
    help_text = DockerProviderBackend.get_build_args_help()
    assert isinstance(help_text, str)
    assert "docker build" in help_text.lower()


def test_backend_start_args_help() -> None:
    help_text = DockerProviderBackend.get_start_args_help()
    assert isinstance(help_text, str)
    assert "docker run" in help_text.lower()


def test_backend_get_config_class() -> None:
    config_class = DockerProviderBackend.get_config_class()
    assert config_class is DockerProviderConfig


def test_build_provider_instance_returns_docker_provider_instance(temp_mngr_ctx: MngrContext) -> None:
    config = DockerProviderConfig()
    instance = DockerProviderBackend.build_provider_instance(
        name=ProviderInstanceName("test-docker"),
        config=config,
        mngr_ctx=temp_mngr_ctx,
    )
    assert isinstance(instance, DockerProviderInstance)


def test_build_provider_instance_with_custom_host_dir(temp_mngr_ctx: MngrContext) -> None:
    config = DockerProviderConfig(host_dir=Path("/custom/dir"))
    instance = DockerProviderBackend.build_provider_instance(
        name=ProviderInstanceName("test-docker"),
        config=config,
        mngr_ctx=temp_mngr_ctx,
    )
    assert instance.host_dir == Path("/custom/dir")


def test_build_provider_instance_uses_default_host_dir(temp_mngr_ctx: MngrContext) -> None:
    config = DockerProviderConfig()
    instance = DockerProviderBackend.build_provider_instance(
        name=ProviderInstanceName("test-docker"),
        config=config,
        mngr_ctx=temp_mngr_ctx,
    )
    assert instance.host_dir == Path("/mngr")


def test_build_provider_instance_uses_name(temp_mngr_ctx: MngrContext) -> None:
    config = DockerProviderConfig()
    instance = DockerProviderBackend.build_provider_instance(
        name=ProviderInstanceName("my-docker"),
        config=config,
        mngr_ctx=temp_mngr_ctx,
    )
    assert instance.name == ProviderInstanceName("my-docker")
