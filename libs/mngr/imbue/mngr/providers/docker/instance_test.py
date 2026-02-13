"""Unit tests for DockerProviderInstance.

These tests do NOT require a Docker daemon. They test pure functions,
capability properties, build args parsing, label helpers, and tag methods.
"""

import json
from pathlib import Path

import pytest

from imbue.mngr.config.data_types import MngrContext
from imbue.mngr.errors import MngrError
from imbue.mngr.primitives import HostId
from imbue.mngr.primitives import HostName
from imbue.mngr.primitives import ProviderInstanceName
from imbue.mngr.primitives import VolumeId
from imbue.mngr.providers.docker.config import DockerProviderConfig
from imbue.mngr.providers.docker.host_store import ContainerConfig
from imbue.mngr.providers.docker.instance import DockerProviderInstance
from imbue.mngr.providers.docker.instance import LABEL_HOST_ID
from imbue.mngr.providers.docker.instance import LABEL_HOST_NAME
from imbue.mngr.providers.docker.instance import LABEL_PROVIDER
from imbue.mngr.providers.docker.instance import LABEL_TAGS
from imbue.mngr.providers.docker.instance import _get_ssh_host_from_docker_config
from imbue.mngr.providers.docker.instance import build_container_labels
from imbue.mngr.providers.docker.instance import parse_container_labels

HOST_ID_A = "host-00000000000000000000000000000001"
HOST_ID_B = "host-00000000000000000000000000000002"


def _make_docker_provider(mngr_ctx: MngrContext, name: str = "test-docker") -> DockerProviderInstance:
    config = DockerProviderConfig()
    return DockerProviderInstance(
        name=ProviderInstanceName(name),
        host_dir=Path("/mngr"),
        mngr_ctx=mngr_ctx,
        config=config,
    )


# =========================================================================
# Capability Properties
# =========================================================================


def test_docker_provider_name(temp_mngr_ctx: MngrContext) -> None:
    provider = _make_docker_provider(temp_mngr_ctx, "my-docker")
    assert provider.name == ProviderInstanceName("my-docker")


def test_docker_provider_supports_snapshots(temp_mngr_ctx: MngrContext) -> None:
    provider = _make_docker_provider(temp_mngr_ctx)
    assert provider.supports_snapshots is True


def test_docker_provider_supports_shutdown_hosts(temp_mngr_ctx: MngrContext) -> None:
    provider = _make_docker_provider(temp_mngr_ctx)
    assert provider.supports_shutdown_hosts is True


def test_docker_provider_does_not_support_volumes(temp_mngr_ctx: MngrContext) -> None:
    provider = _make_docker_provider(temp_mngr_ctx)
    assert provider.supports_volumes is False


def test_docker_provider_does_not_support_mutable_tags(temp_mngr_ctx: MngrContext) -> None:
    provider = _make_docker_provider(temp_mngr_ctx)
    assert provider.supports_mutable_tags is False


def test_list_volumes_returns_empty_list(temp_mngr_ctx: MngrContext) -> None:
    provider = _make_docker_provider(temp_mngr_ctx)
    assert provider.list_volumes() == []


# =========================================================================
# Container Label Helpers
# =========================================================================


def test_build_container_labels_with_no_tags() -> None:
    labels = build_container_labels(
        host_id=HostId(HOST_ID_A),
        name=HostName("test-host"),
        provider_name="docker",
    )
    assert labels[LABEL_HOST_ID] == HOST_ID_A
    assert labels[LABEL_HOST_NAME] == "test-host"
    assert labels[LABEL_PROVIDER] == "docker"
    assert json.loads(labels[LABEL_TAGS]) == {}


def test_build_container_labels_with_tags() -> None:
    labels = build_container_labels(
        host_id=HostId(HOST_ID_A),
        name=HostName("test-host"),
        provider_name="docker",
        user_tags={"env": "test", "team": "infra"},
    )
    assert json.loads(labels[LABEL_TAGS]) == {"env": "test", "team": "infra"}


def test_parse_container_labels_extracts_host_id_and_name() -> None:
    labels = {
        LABEL_HOST_ID: HOST_ID_A,
        LABEL_HOST_NAME: "my-host",
        LABEL_PROVIDER: "docker",
        LABEL_TAGS: "{}",
    }
    host_id, name, provider, tags = parse_container_labels(labels)
    assert host_id == HostId(HOST_ID_A)
    assert name == HostName("my-host")
    assert provider == "docker"


def test_parse_container_labels_extracts_tags() -> None:
    labels = {
        LABEL_HOST_ID: HOST_ID_A,
        LABEL_HOST_NAME: "my-host",
        LABEL_PROVIDER: "docker",
        LABEL_TAGS: '{"env": "prod", "version": "2"}',
    }
    _, _, _, tags = parse_container_labels(labels)
    assert tags == {"env": "prod", "version": "2"}


def test_build_and_parse_container_labels_roundtrip() -> None:
    host_id = HostId(HOST_ID_B)
    name = HostName("roundtrip-host")
    provider = "my-docker-provider"
    user_tags = {"key1": "val1", "key2": "val2"}

    labels = build_container_labels(host_id, name, provider, user_tags)
    parsed_host_id, parsed_name, parsed_provider, parsed_tags = parse_container_labels(labels)

    assert parsed_host_id == host_id
    assert parsed_name == name
    assert parsed_provider == provider
    assert parsed_tags == user_tags


def test_parse_container_labels_handles_missing_tags_label() -> None:
    labels = {
        LABEL_HOST_ID: HOST_ID_A,
        LABEL_HOST_NAME: "my-host",
        LABEL_PROVIDER: "docker",
    }
    _, _, _, tags = parse_container_labels(labels)
    assert tags == {}


def test_parse_container_labels_handles_invalid_tags_json() -> None:
    labels = {
        LABEL_HOST_ID: HOST_ID_A,
        LABEL_HOST_NAME: "my-host",
        LABEL_PROVIDER: "docker",
        LABEL_TAGS: "not valid json {{{",
    }
    _, _, _, tags = parse_container_labels(labels)
    assert tags == {}


# =========================================================================
# SSH Host Resolution
# =========================================================================


def test_get_ssh_host_local_docker_empty_string() -> None:
    assert _get_ssh_host_from_docker_config("") == "127.0.0.1"


def test_get_ssh_host_local_docker_unix_socket() -> None:
    assert _get_ssh_host_from_docker_config("unix:///var/run/docker.sock") == "127.0.0.1"


def test_get_ssh_host_remote_docker_ssh() -> None:
    assert _get_ssh_host_from_docker_config("ssh://user@myserver") == "myserver"


def test_get_ssh_host_remote_docker_tcp() -> None:
    assert _get_ssh_host_from_docker_config("tcp://192.168.1.100:2376") == "192.168.1.100"


# =========================================================================
# Build Args Parsing
# =========================================================================


def test_parse_build_args_empty(temp_mngr_ctx: MngrContext) -> None:
    provider = _make_docker_provider(temp_mngr_ctx)
    config = provider._parse_build_args(None)
    assert isinstance(config, ContainerConfig)
    assert config.cpu == 1.0
    assert config.memory == 1.0
    assert config.gpu is None
    assert config.image is None


def test_parse_build_args_empty_list(temp_mngr_ctx: MngrContext) -> None:
    provider = _make_docker_provider(temp_mngr_ctx)
    config = provider._parse_build_args([])
    assert config.cpu == 1.0
    assert config.memory == 1.0


def test_parse_build_args_key_value_format(temp_mngr_ctx: MngrContext) -> None:
    provider = _make_docker_provider(temp_mngr_ctx)
    config = provider._parse_build_args(["cpu=2", "memory=8"])
    assert config.cpu == 2.0
    assert config.memory == 8.0


def test_parse_build_args_flag_equals_format(temp_mngr_ctx: MngrContext) -> None:
    provider = _make_docker_provider(temp_mngr_ctx)
    config = provider._parse_build_args(["--cpu=2", "--memory=8", "--gpu=nvidia"])
    assert config.cpu == 2.0
    assert config.memory == 8.0
    assert config.gpu == "nvidia"


def test_parse_build_args_flag_space_format(temp_mngr_ctx: MngrContext) -> None:
    provider = _make_docker_provider(temp_mngr_ctx)
    config = provider._parse_build_args(["--cpu", "2", "--memory", "8"])
    assert config.cpu == 2.0
    assert config.memory == 8.0


def test_parse_build_args_mixed_formats(temp_mngr_ctx: MngrContext) -> None:
    provider = _make_docker_provider(temp_mngr_ctx)
    config = provider._parse_build_args(["cpu=4", "--memory=16"])
    assert config.cpu == 4.0
    assert config.memory == 16.0


def test_parse_build_args_image(temp_mngr_ctx: MngrContext) -> None:
    provider = _make_docker_provider(temp_mngr_ctx)
    config = provider._parse_build_args(["--image=python:3.11-slim"])
    assert config.image == "python:3.11-slim"


def test_parse_build_args_dockerfile(temp_mngr_ctx: MngrContext) -> None:
    provider = _make_docker_provider(temp_mngr_ctx)
    config = provider._parse_build_args(["--dockerfile=/path/to/Dockerfile"])
    assert config.dockerfile == "/path/to/Dockerfile"


def test_parse_build_args_context_dir(temp_mngr_ctx: MngrContext) -> None:
    provider = _make_docker_provider(temp_mngr_ctx)
    config = provider._parse_build_args(["--context-dir=/path/to/context"])
    assert config.context_dir == "/path/to/context"


def test_parse_build_args_network(temp_mngr_ctx: MngrContext) -> None:
    provider = _make_docker_provider(temp_mngr_ctx)
    config = provider._parse_build_args(["--network=my-network"])
    assert config.network == "my-network"


def test_parse_build_args_volume_single(temp_mngr_ctx: MngrContext) -> None:
    provider = _make_docker_provider(temp_mngr_ctx)
    config = provider._parse_build_args(["--volume=/host:/container"])
    assert config.volumes == ("/host:/container",)


def test_parse_build_args_volume_multiple(temp_mngr_ctx: MngrContext) -> None:
    provider = _make_docker_provider(temp_mngr_ctx)
    config = provider._parse_build_args(["--volume=/a:/b", "--volume=/c:/d"])
    assert config.volumes == ("/a:/b", "/c:/d")


def test_parse_build_args_port_single(temp_mngr_ctx: MngrContext) -> None:
    provider = _make_docker_provider(temp_mngr_ctx)
    config = provider._parse_build_args(["--port=8080:80"])
    assert config.ports == ("8080:80",)


def test_parse_build_args_port_multiple(temp_mngr_ctx: MngrContext) -> None:
    provider = _make_docker_provider(temp_mngr_ctx)
    config = provider._parse_build_args(["--port=8080:80", "--port=9090:90"])
    assert config.ports == ("8080:80", "9090:90")


def test_parse_build_args_unknown_raises_error(temp_mngr_ctx: MngrContext) -> None:
    provider = _make_docker_provider(temp_mngr_ctx)
    with pytest.raises(MngrError, match="Unknown build arguments"):
        provider._parse_build_args(["--foobar=baz"])


def test_parse_build_args_uses_config_default_gpu(temp_mngr_ctx: MngrContext) -> None:
    config = DockerProviderConfig(default_gpu="nvidia")
    provider = DockerProviderInstance(
        name=ProviderInstanceName("test-docker"),
        host_dir=Path("/mngr"),
        mngr_ctx=temp_mngr_ctx,
        config=config,
    )
    result = provider._parse_build_args(None)
    assert result.gpu == "nvidia"


def test_parse_build_args_uses_config_default_image(temp_mngr_ctx: MngrContext) -> None:
    config = DockerProviderConfig(default_image="ubuntu:22.04")
    provider = DockerProviderInstance(
        name=ProviderInstanceName("test-docker"),
        host_dir=Path("/mngr"),
        mngr_ctx=temp_mngr_ctx,
        config=config,
    )
    result = provider._parse_build_args(None)
    assert result.image == "ubuntu:22.04"


def test_parse_build_args_explicit_args_override_config_defaults(temp_mngr_ctx: MngrContext) -> None:
    config = DockerProviderConfig(default_gpu="nvidia", default_cpu=8.0)
    provider = DockerProviderInstance(
        name=ProviderInstanceName("test-docker"),
        host_dir=Path("/mngr"),
        mngr_ctx=temp_mngr_ctx,
        config=config,
    )
    result = provider._parse_build_args(["--gpu=amd", "--cpu=2"])
    assert result.gpu == "amd"
    assert result.cpu == 2.0


# =========================================================================
# Tag Methods (no Docker required)
# =========================================================================


def test_set_host_tags_raises_mngr_error(temp_mngr_ctx: MngrContext) -> None:
    provider = _make_docker_provider(temp_mngr_ctx)
    with pytest.raises(MngrError, match="does not support mutable tags"):
        provider.set_host_tags(HostId(HOST_ID_A), {"key": "val"})


def test_add_tags_to_host_raises_mngr_error(temp_mngr_ctx: MngrContext) -> None:
    provider = _make_docker_provider(temp_mngr_ctx)
    with pytest.raises(MngrError, match="does not support mutable tags"):
        provider.add_tags_to_host(HostId(HOST_ID_A), {"key": "val"})


def test_remove_tags_from_host_raises_mngr_error(temp_mngr_ctx: MngrContext) -> None:
    provider = _make_docker_provider(temp_mngr_ctx)
    with pytest.raises(MngrError, match="does not support mutable tags"):
        provider.remove_tags_from_host(HostId(HOST_ID_A), ["key"])


def test_delete_volume_raises_not_implemented(temp_mngr_ctx: MngrContext) -> None:
    provider = _make_docker_provider(temp_mngr_ctx)
    with pytest.raises(NotImplementedError):
        provider.delete_volume(VolumeId("vol-00000000000000000000000000000001"))
