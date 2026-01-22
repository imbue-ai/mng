"""Unit tests for the DockerProviderInstance.

These tests mock the Docker CLI to avoid requiring Docker to be installed.
"""

import json
from pathlib import Path
from unittest.mock import MagicMock
from unittest.mock import patch

import pluggy
import pytest

from imbue.mngr.config.data_types import MngrConfig
from imbue.mngr.config.data_types import MngrContext
from imbue.mngr.errors import HostNotFoundError
from imbue.mngr.errors import MngrError
from imbue.mngr.errors import SnapshotNotFoundError
from imbue.mngr.primitives import HostId
from imbue.mngr.primitives import HostName
from imbue.mngr.primitives import ProviderInstanceName
from imbue.mngr.primitives import SnapshotId
from imbue.mngr.primitives import VolumeId
from imbue.mngr.providers.docker.instance import ContainerConfig
from imbue.mngr.providers.docker.instance import DEFAULT_IMAGE
from imbue.mngr.providers.docker.instance import DockerProviderInstance
from imbue.mngr.providers.docker.instance import LABEL_HOST_ID
from imbue.mngr.providers.docker.instance import LABEL_HOST_NAME
from imbue.mngr.providers.docker.instance import LABEL_HOST_RECORD


@pytest.fixture
def docker_provider(tmp_path: Path, mngr_test_id: str) -> DockerProviderInstance:
    """Create a DockerProviderInstance for testing."""
    config = MngrConfig(
        default_host_dir=tmp_path / "mngr",
        prefix=f"mngr-test-{mngr_test_id}-",
    )
    pm = pluggy.PluginManager("mngr")
    mngr_ctx = MngrContext(config=config, pm=pm)

    return DockerProviderInstance(
        name=ProviderInstanceName("docker"),
        host_dir=Path("/mngr"),
        mngr_ctx=mngr_ctx,
        container_prefix=f"mngr-test-{mngr_test_id}",
        default_cpu=None,
        default_memory=None,
    )


def test_docker_provider_name(docker_provider: DockerProviderInstance) -> None:
    """Test that the provider name is set correctly."""
    assert docker_provider.name == ProviderInstanceName("docker")


def test_docker_provider_supports_snapshots(docker_provider: DockerProviderInstance) -> None:
    """Test that docker provider does not support snapshots."""
    assert docker_provider.supports_snapshots is False


def test_docker_provider_supports_volumes(docker_provider: DockerProviderInstance) -> None:
    """Test that docker provider does not support volumes."""
    assert docker_provider.supports_volumes is False


def test_docker_provider_supports_mutable_tags(docker_provider: DockerProviderInstance) -> None:
    """Test that docker provider supports mutable tags."""
    assert docker_provider.supports_mutable_tags is True


def test_parse_build_args_empty(docker_provider: DockerProviderInstance) -> None:
    """Test parsing empty build args."""
    config = docker_provider._parse_build_args(None)
    assert config.cpu is None
    assert config.memory is None
    assert config.image == DEFAULT_IMAGE


def test_parse_build_args_with_cpu(docker_provider: DockerProviderInstance) -> None:
    """Test parsing build args with CPU."""
    config = docker_provider._parse_build_args(["--cpu", "2.0"])
    assert config.cpu == 2.0
    assert config.memory is None


def test_parse_build_args_with_memory(docker_provider: DockerProviderInstance) -> None:
    """Test parsing build args with memory."""
    config = docker_provider._parse_build_args(["--memory", "4.0"])
    assert config.memory == 4.0
    assert config.cpu is None


def test_parse_build_args_with_image(docker_provider: DockerProviderInstance) -> None:
    """Test parsing build args with custom image."""
    config = docker_provider._parse_build_args(["--image", "python:3.11"])
    assert config.image == "python:3.11"


def test_parse_build_args_with_equals_format(docker_provider: DockerProviderInstance) -> None:
    """Test parsing build args with equals format (cpu=2.0)."""
    config = docker_provider._parse_build_args(["cpu=2.0"])
    assert config.cpu == 2.0


def test_parse_build_args_unknown_raises_error(docker_provider: DockerProviderInstance) -> None:
    """Test that unknown build args raise an error."""
    with pytest.raises(MngrError, match="Unknown build arguments"):
        docker_provider._parse_build_args(["--unknown", "value"])


def test_container_config_defaults() -> None:
    """Test ContainerConfig default values."""
    config = ContainerConfig()
    assert config.cpu is None
    assert config.memory is None
    assert config.image == DEFAULT_IMAGE


def test_list_volumes_returns_empty(docker_provider: DockerProviderInstance) -> None:
    """Test that list_volumes returns empty list."""
    volumes = docker_provider.list_volumes()
    assert volumes == []


def test_list_snapshots_returns_empty(docker_provider: DockerProviderInstance) -> None:
    """Test that list_snapshots returns empty list."""
    snapshots = docker_provider.list_snapshots(HostId.generate())
    assert snapshots == []


def test_close_does_nothing(docker_provider: DockerProviderInstance) -> None:
    """Test that close is a no-op."""
    # Should not raise
    docker_provider.close()


def test_tag_management(docker_provider: DockerProviderInstance, tmp_path: Path) -> None:
    """Test tag loading and saving."""
    host_id = HostId.generate()

    # Initially empty
    tags = docker_provider._load_tags(host_id)
    assert tags == {}

    # Save tags
    docker_provider._save_tags(host_id, {"env": "test", "team": "backend"})

    # Load tags
    tags = docker_provider._load_tags(host_id)
    assert tags["env"] == "test"
    assert tags["team"] == "backend"

    # Delete host data
    docker_provider._delete_host_data(host_id)

    # Tags should be gone
    tags = docker_provider._load_tags(host_id)
    assert tags == {}


def test_build_container_labels(docker_provider: DockerProviderInstance) -> None:
    """Test building container labels."""
    host_id = HostId.generate()
    name = HostName("test-host")
    config = ContainerConfig()

    labels = docker_provider._build_container_labels(
        host_id=host_id,
        name=name,
        ssh_port=22,
        host_public_key="ssh-ed25519 AAAA...",
        config=config,
    )

    assert LABEL_HOST_ID in labels
    assert labels[LABEL_HOST_ID] == str(host_id)
    assert LABEL_HOST_NAME in labels
    assert labels[LABEL_HOST_NAME] == str(name)
    assert LABEL_HOST_RECORD in labels


def test_parse_container_labels(docker_provider: DockerProviderInstance) -> None:
    """Test parsing container labels."""
    host_id = HostId.generate()
    name = HostName("test-host")
    config = ContainerConfig(cpu=2.0, memory=4.0, image="python:3.11")

    labels = docker_provider._build_container_labels(
        host_id=host_id,
        name=name,
        ssh_port=2222,
        host_public_key="ssh-ed25519 AAAA...",
        config=config,
    )

    parsed_host_id, parsed_name, ssh_port, host_public_key, parsed_config = docker_provider._parse_container_labels(
        labels
    )

    assert parsed_host_id == host_id
    assert parsed_name == name
    assert ssh_port == 2222
    assert host_public_key == "ssh-ed25519 AAAA..."
    assert parsed_config.cpu == 2.0
    assert parsed_config.memory == 4.0
    assert parsed_config.image == "python:3.11"


@patch("subprocess.run")
def test_list_hosts_with_no_containers(mock_run: MagicMock, docker_provider: DockerProviderInstance) -> None:
    """Test listing hosts when there are no containers."""
    mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="")

    hosts = docker_provider.list_hosts()
    assert hosts == []


@patch("subprocess.run")
def test_run_docker_command_failure(mock_run: MagicMock, docker_provider: DockerProviderInstance) -> None:
    """Test that docker command failures raise MngrError."""
    from subprocess import CalledProcessError

    mock_run.side_effect = CalledProcessError(1, "docker", stderr="error message")

    with pytest.raises(MngrError, match="Docker command failed"):
        docker_provider._run_docker_command(["info"])


def test_get_container_name(docker_provider: DockerProviderInstance) -> None:
    """Test generating container names from host IDs."""
    host_id = HostId.generate()
    container_name = docker_provider._get_container_name(host_id)
    assert container_name.startswith(docker_provider.container_prefix)
    assert str(host_id)[-8:] in container_name


@patch("subprocess.run")
def test_find_container_by_host_id_not_found(mock_run: MagicMock, docker_provider: DockerProviderInstance) -> None:
    """Test finding a container by host ID when not found."""
    mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="")

    result = docker_provider._find_container_by_host_id(HostId.generate())
    assert result is None


@patch("subprocess.run")
def test_find_container_by_host_id_found(mock_run: MagicMock, docker_provider: DockerProviderInstance) -> None:
    """Test finding a container by host ID when found."""
    host_id = HostId.generate()
    container_info = {"Names": "test-container", "ID": "abc123"}
    mock_run.return_value = MagicMock(returncode=0, stdout=json.dumps(container_info), stderr="")

    result = docker_provider._find_container_by_host_id(host_id)
    assert result == container_info


@patch("subprocess.run")
def test_find_container_by_name_not_found(mock_run: MagicMock, docker_provider: DockerProviderInstance) -> None:
    """Test finding a container by name when not found."""
    mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="")

    result = docker_provider._find_container_by_name(HostName("test-host"))
    assert result is None


@patch("subprocess.run")
def test_find_container_by_name_found(mock_run: MagicMock, docker_provider: DockerProviderInstance) -> None:
    """Test finding a container by name when found."""
    container_info = {"Names": "test-container", "ID": "abc123"}
    mock_run.return_value = MagicMock(returncode=0, stdout=json.dumps(container_info), stderr="")

    result = docker_provider._find_container_by_name(HostName("test-host"))
    assert result == container_info


@patch("subprocess.run")
def test_is_container_running_true(mock_run: MagicMock, docker_provider: DockerProviderInstance) -> None:
    """Test checking if container is running when it is."""
    mock_run.return_value = MagicMock(returncode=0, stdout="true", stderr="")

    result = docker_provider._is_container_running("test-container")
    assert result is True


@patch("subprocess.run")
def test_is_container_running_false(mock_run: MagicMock, docker_provider: DockerProviderInstance) -> None:
    """Test checking if container is running when it is not."""
    mock_run.return_value = MagicMock(returncode=0, stdout="false", stderr="")

    result = docker_provider._is_container_running("test-container")
    assert result is False


@patch("subprocess.run")
def test_get_container_port_mapping(mock_run: MagicMock, docker_provider: DockerProviderInstance) -> None:
    """Test getting container port mapping."""
    mock_run.return_value = MagicMock(returncode=0, stdout="0.0.0.0:32768", stderr="")

    port = docker_provider._get_container_port_mapping("test-container")
    assert port == 32768


@patch("subprocess.run")
def test_get_container_port_mapping_ipv6(mock_run: MagicMock, docker_provider: DockerProviderInstance) -> None:
    """Test getting container port mapping with IPv6."""
    mock_run.return_value = MagicMock(returncode=0, stdout="[::]:32769", stderr="")

    port = docker_provider._get_container_port_mapping("test-container")
    assert port == 32769


@patch("subprocess.run")
def test_get_container_port_mapping_not_found(mock_run: MagicMock, docker_provider: DockerProviderInstance) -> None:
    """Test getting container port mapping when not found."""
    mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="")

    port = docker_provider._get_container_port_mapping("test-container")
    assert port is None


@patch("subprocess.run")
def test_get_container_labels(mock_run: MagicMock, docker_provider: DockerProviderInstance) -> None:
    """Test getting container labels."""
    labels = {"mngr.host_id": "host-123", "mngr.host_name": "test"}
    mock_run.return_value = MagicMock(returncode=0, stdout=json.dumps(labels), stderr="")

    result = docker_provider._get_container_labels("test-container")
    assert result == labels


@patch("subprocess.run")
def test_get_container_labels_not_found(mock_run: MagicMock, docker_provider: DockerProviderInstance) -> None:
    """Test getting container labels when container not found."""
    mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="")

    result = docker_provider._get_container_labels("test-container")
    assert result == {}


def test_create_snapshot_raises_not_implemented(docker_provider: DockerProviderInstance) -> None:
    """Test that create_snapshot raises NotImplementedError."""
    with pytest.raises(NotImplementedError):
        docker_provider.create_snapshot(HostId.generate())


def test_delete_snapshot_raises_not_found(docker_provider: DockerProviderInstance) -> None:
    """Test that delete_snapshot raises SnapshotNotFoundError."""
    with pytest.raises(SnapshotNotFoundError):
        docker_provider.delete_snapshot(HostId.generate(), SnapshotId.generate())


def test_delete_volume_raises_not_implemented(docker_provider: DockerProviderInstance) -> None:
    """Test that delete_volume raises NotImplementedError."""
    with pytest.raises(NotImplementedError):
        docker_provider.delete_volume(VolumeId.generate())


@patch("subprocess.run")
def test_stop_host_not_found(mock_run: MagicMock, docker_provider: DockerProviderInstance) -> None:
    """Test stopping a host that doesn't exist."""
    mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="")

    # Should not raise, just log
    docker_provider.stop_host(HostId.generate())


@patch("subprocess.run")
def test_destroy_host_not_found(mock_run: MagicMock, docker_provider: DockerProviderInstance) -> None:
    """Test destroying a host that doesn't exist."""
    mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="")

    # Should not raise, just clean up local data
    docker_provider.destroy_host(HostId.generate())


@patch("subprocess.run")
def test_get_host_by_id_not_found(mock_run: MagicMock, docker_provider: DockerProviderInstance) -> None:
    """Test getting a host by ID when not found."""
    mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="")

    with pytest.raises(HostNotFoundError):
        docker_provider.get_host(HostId.generate())


@patch("subprocess.run")
def test_get_host_by_name_not_found(mock_run: MagicMock, docker_provider: DockerProviderInstance) -> None:
    """Test getting a host by name when not found."""
    mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="")

    with pytest.raises(HostNotFoundError):
        docker_provider.get_host(HostName("nonexistent"))


@patch("subprocess.run")
def test_start_host_not_found(mock_run: MagicMock, docker_provider: DockerProviderInstance) -> None:
    """Test starting a host that doesn't exist."""
    mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="")

    with pytest.raises(HostNotFoundError):
        docker_provider.start_host(HostId.generate())


@patch("subprocess.run")
def test_get_connector_not_found(mock_run: MagicMock, docker_provider: DockerProviderInstance) -> None:
    """Test getting connector for host that doesn't exist."""
    mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="")

    with pytest.raises(HostNotFoundError):
        docker_provider.get_connector(HostId.generate())


@patch("subprocess.run")
def test_rename_host_not_found(mock_run: MagicMock, docker_provider: DockerProviderInstance) -> None:
    """Test renaming a host that doesn't exist."""
    mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="")

    with pytest.raises(HostNotFoundError):
        docker_provider.rename_host(HostId.generate(), HostName("new-name"))


@patch("subprocess.run")
def test_get_host_resources_no_container(mock_run: MagicMock, docker_provider: DockerProviderInstance) -> None:
    """Test getting host resources when container not found."""
    from imbue.mngr.hosts.host import Host
    from imbue.mngr.interfaces.data_types import PyinfraConnector
    from pyinfra.api import State as PyinfraState
    from pyinfra.api.inventory import Inventory

    mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="")

    # Create a mock Host object
    inventory = Inventory(([("localhost", {})], {}))
    state = PyinfraState(inventory=inventory)
    pyinfra_host = inventory.get_host("localhost")
    pyinfra_host.init(state)
    connector = PyinfraConnector(pyinfra_host)

    host = Host(
        id=HostId.generate(),
        connector=connector,
        provider_instance=docker_provider,
        mngr_ctx=docker_provider.mngr_ctx,
    )

    resources = docker_provider.get_host_resources(host)
    assert resources.cpu.count == 1
    assert resources.memory_gb == 1.0


def test_keys_dir(docker_provider: DockerProviderInstance) -> None:
    """Test that _keys_dir returns the correct path."""
    keys_dir = docker_provider._keys_dir
    assert "providers" in str(keys_dir)
    assert "docker" in str(keys_dir)


def test_data_dir(docker_provider: DockerProviderInstance) -> None:
    """Test that _data_dir returns the correct path."""
    data_dir = docker_provider._data_dir
    assert "hosts" in str(data_dir)


def test_known_hosts_path(docker_provider: DockerProviderInstance) -> None:
    """Test that _known_hosts_path returns the correct path."""
    known_hosts_path = docker_provider._known_hosts_path
    assert "known_hosts" in str(known_hosts_path)


@patch("subprocess.run")
def test_docker_exec(mock_run: MagicMock, docker_provider: DockerProviderInstance) -> None:
    """Test executing a command in a container."""
    mock_run.return_value = MagicMock(returncode=0, stdout="hello", stderr="")

    result = docker_provider._docker_exec("test-container", ["echo", "hello"])
    assert result.stdout == "hello"


def test_get_host_data_dir(docker_provider: DockerProviderInstance) -> None:
    """Test that _get_host_data_dir returns the correct path."""
    host_id = HostId.generate()
    host_data_dir = docker_provider._get_host_data_dir(host_id)
    assert str(host_id) in str(host_data_dir)


def test_get_tags_file_path(docker_provider: DockerProviderInstance) -> None:
    """Test that _get_tags_file_path returns the correct path."""
    host_id = HostId.generate()
    tags_file = docker_provider._get_tags_file_path(host_id)
    assert "tags.json" in str(tags_file)


@patch("subprocess.run")
def test_list_mngr_containers_empty(mock_run: MagicMock, docker_provider: DockerProviderInstance) -> None:
    """Test listing mngr containers when none exist."""
    mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

    containers = docker_provider._list_mngr_containers()
    assert containers == []


@patch("subprocess.run")
def test_list_mngr_containers_with_data(mock_run: MagicMock, docker_provider: DockerProviderInstance) -> None:
    """Test listing mngr containers when some exist."""
    container1 = json.dumps({"Names": "test-1", "ID": "abc123"})
    container2 = json.dumps({"Names": "test-2", "ID": "def456"})
    mock_run.return_value = MagicMock(returncode=0, stdout=f"{container1}\n{container2}", stderr="")

    containers = docker_provider._list_mngr_containers()
    assert len(containers) == 2
