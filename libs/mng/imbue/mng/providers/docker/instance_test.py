import json

import pytest

from imbue.mng.config.data_types import MngContext
from imbue.mng.errors import MngError
from imbue.mng.primitives import HostId
from imbue.mng.primitives import HostName
from imbue.mng.primitives import ProviderInstanceName
from imbue.mng.providers.docker.instance import CONTAINER_SSH_PORT
from imbue.mng.providers.docker.instance import LABEL_HOST_ID
from imbue.mng.providers.docker.instance import LABEL_HOST_NAME
from imbue.mng.providers.docker.instance import LABEL_PROVIDER
from imbue.mng.providers.docker.instance import LABEL_TAGS
from imbue.mng.providers.docker.instance import _get_ssh_host_from_docker_config
from imbue.mng.providers.docker.instance import build_container_labels
from imbue.mng.providers.docker.instance import parse_container_labels
from imbue.mng.providers.docker.testing import make_docker_provider

HOST_ID_A = "host-00000000000000000000000000000001"
HOST_ID_B = "host-00000000000000000000000000000002"


# =========================================================================
# Capability Properties
# =========================================================================


def test_docker_provider_name(temp_mng_ctx: MngContext) -> None:
    provider = make_docker_provider(temp_mng_ctx, "my-docker")
    assert provider.name == ProviderInstanceName("my-docker")


def test_docker_provider_supports_snapshots(temp_mng_ctx: MngContext) -> None:
    provider = make_docker_provider(temp_mng_ctx)
    assert provider.supports_snapshots is True


def test_docker_provider_supports_shutdown_hosts(temp_mng_ctx: MngContext) -> None:
    provider = make_docker_provider(temp_mng_ctx)
    assert provider.supports_shutdown_hosts is True


def test_docker_provider_supports_volumes(temp_mng_ctx: MngContext) -> None:
    provider = make_docker_provider(temp_mng_ctx)
    assert provider.supports_volumes is True


def test_docker_provider_does_not_support_mutable_tags(temp_mng_ctx: MngContext) -> None:
    provider = make_docker_provider(temp_mng_ctx)
    assert provider.supports_mutable_tags is False


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
# Docker Run Command Building
# =========================================================================


def test_build_docker_run_command_includes_mandatory_flags(temp_mng_ctx: MngContext) -> None:
    provider = make_docker_provider(temp_mng_ctx)
    cmd = provider._build_docker_run_command(
        image="debian:bookworm-slim",
        container_name="test-container",
        labels={"com.imbue.mng.host-id": HOST_ID_A},
        start_args=(),
    )
    assert "run" in cmd
    assert "-d" in cmd
    assert "--name" in cmd
    assert "test-container" in cmd
    assert f":{CONTAINER_SSH_PORT}" in cmd
    assert "debian:bookworm-slim" in cmd


def test_build_docker_run_command_includes_labels(temp_mng_ctx: MngContext) -> None:
    provider = make_docker_provider(temp_mng_ctx)
    cmd = provider._build_docker_run_command(
        image="debian:bookworm-slim",
        container_name="test",
        labels={"key1": "val1", "key2": "val2"},
        start_args=(),
    )
    assert "--label" in cmd
    label_indices = [i for i, arg in enumerate(cmd) if arg == "--label"]
    label_values = [cmd[i + 1] for i in label_indices]
    assert "key1=val1" in label_values
    assert "key2=val2" in label_values


def test_build_docker_run_command_passes_through_start_args(temp_mng_ctx: MngContext) -> None:
    provider = make_docker_provider(temp_mng_ctx)
    cmd = provider._build_docker_run_command(
        image="debian:bookworm-slim",
        container_name="test",
        labels={},
        start_args=("--cpus=2", "--memory=4g", "--gpus=all"),
    )
    assert "--cpus=2" in cmd
    assert "--memory=4g" in cmd
    assert "--gpus=all" in cmd


def test_build_docker_run_command_entrypoint_at_end(temp_mng_ctx: MngContext) -> None:
    provider = make_docker_provider(temp_mng_ctx)
    cmd = provider._build_docker_run_command(
        image="my-image",
        container_name="test",
        labels={},
        start_args=(),
    )
    # Image and entrypoint should be at the end: --entrypoint sh <image> -c <cmd>
    image_idx = cmd.index("my-image")
    assert cmd[image_idx - 1] == "sh"
    assert cmd[image_idx + 1] == "-c"


# =========================================================================
# Tag Methods (no Docker required)
# =========================================================================


def test_set_host_tags_raises_mng_error(temp_mng_ctx: MngContext) -> None:
    provider = make_docker_provider(temp_mng_ctx)
    with pytest.raises(MngError, match="does not support mutable tags"):
        provider.set_host_tags(HostId(HOST_ID_A), {"key": "val"})


def test_add_tags_to_host_raises_mng_error(temp_mng_ctx: MngContext) -> None:
    provider = make_docker_provider(temp_mng_ctx)
    with pytest.raises(MngError, match="does not support mutable tags"):
        provider.add_tags_to_host(HostId(HOST_ID_A), {"key": "val"})


def test_remove_tags_from_host_raises_mng_error(temp_mng_ctx: MngContext) -> None:
    provider = make_docker_provider(temp_mng_ctx)
    with pytest.raises(MngError, match="does not support mutable tags"):
        provider.remove_tags_from_host(HostId(HOST_ID_A), ["key"])
