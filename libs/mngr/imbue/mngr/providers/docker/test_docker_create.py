"""Integration tests for creating hosts on Docker.

These tests require Docker to be installed and running. They create actual
Docker containers and clean them up after each test.
"""

import subprocess
import tempfile
from collections.abc import Generator
from pathlib import Path
from uuid import uuid4

import pluggy
import pytest

from imbue.mngr.config.data_types import MngrConfig
from imbue.mngr.config.data_types import MngrContext
from imbue.mngr.primitives import HostName
from imbue.mngr.primitives import ProviderInstanceName
from imbue.mngr.providers.docker.instance import DockerProviderInstance


def is_docker_available() -> bool:
    """Check if Docker is available and running."""
    try:
        result = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            timeout=10,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


# Skip all tests in this module if Docker is not available
pytestmark = pytest.mark.skipif(
    not is_docker_available(),
    reason="Docker is not available",
)


@pytest.fixture
def docker_test_id() -> str:
    """Generate a unique test ID for isolation."""
    return uuid4().hex[:8]


@pytest.fixture
def docker_provider(
    tmp_path: Path,
    docker_test_id: str,
) -> Generator[DockerProviderInstance, None, None]:
    """Create a DockerProviderInstance for testing."""
    config = MngrConfig(
        default_host_dir=tmp_path / "mngr",
        prefix=f"mngr-test-{docker_test_id}-",
    )
    pm = pluggy.PluginManager("mngr")
    mngr_ctx = MngrContext(config=config, pm=pm)

    provider = DockerProviderInstance(
        name=ProviderInstanceName("docker"),
        host_dir=Path("/mngr"),
        mngr_ctx=mngr_ctx,
        container_prefix=f"mngr-test-{docker_test_id}",
        default_cpu=None,
        default_memory=None,
    )

    yield provider

    # Clean up all containers created by this test
    try:
        result = subprocess.run(
            [
                "docker",
                "ps",
                "-a",
                "--filter",
                f"name=mngr-test-{docker_test_id}",
                "--format",
                "{{.Names}}",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0 and result.stdout.strip():
            for container_name in result.stdout.strip().split("\n"):
                if container_name:
                    subprocess.run(
                        ["docker", "rm", "-f", container_name],
                        capture_output=True,
                        timeout=30,
                    )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    provider.close()


@pytest.fixture
def temp_source_dir() -> Generator[Path, None, None]:
    """Create a temporary source directory for tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        source_dir = Path(tmpdir)
        (source_dir / "test.txt").write_text("test content")
        yield source_dir


@pytest.mark.timeout(300)
def test_docker_create_host(docker_provider: DockerProviderInstance) -> None:
    """Test creating a Docker container host."""
    host = docker_provider.create_host(HostName("test-host"))

    assert host is not None
    assert host.id is not None

    # Verify we can execute a command on the host
    result = host.execute_command("echo hello")
    assert result.success
    assert "hello" in result.stdout


@pytest.mark.timeout(300)
def test_docker_host_list_hosts(docker_provider: DockerProviderInstance) -> None:
    """Test listing Docker container hosts."""
    host = docker_provider.create_host(HostName("test-host"))

    hosts = docker_provider.list_hosts()

    assert len(hosts) >= 1
    host_ids = [h.id for h in hosts]
    assert host.id in host_ids


@pytest.mark.timeout(300)
def test_docker_host_get_host_by_id(docker_provider: DockerProviderInstance) -> None:
    """Test getting a Docker container host by ID."""
    host = docker_provider.create_host(HostName("test-host"))

    retrieved_host = docker_provider.get_host(host.id)

    assert retrieved_host.id == host.id


@pytest.mark.timeout(300)
def test_docker_host_stop_and_start(docker_provider: DockerProviderInstance) -> None:
    """Test stopping and starting a Docker container host."""
    host = docker_provider.create_host(HostName("test-host"))

    # Stop the host
    docker_provider.stop_host(host)

    # Start the host again
    restarted_host = docker_provider.start_host(host.id)

    # Verify we can execute a command on the restarted host
    result = restarted_host.execute_command("echo hello")
    assert result.success
    assert "hello" in result.stdout


@pytest.mark.timeout(300)
def test_docker_host_destroy(docker_provider: DockerProviderInstance) -> None:
    """Test destroying a Docker container host."""
    host = docker_provider.create_host(HostName("test-host"))
    host_id = host.id

    docker_provider.destroy_host(host)

    # Verify host is no longer in the list
    hosts = docker_provider.list_hosts()
    host_ids = [h.id for h in hosts]
    assert host_id not in host_ids


@pytest.mark.timeout(300)
def test_docker_host_tags(docker_provider: DockerProviderInstance) -> None:
    """Test tag management on Docker container hosts."""
    host = docker_provider.create_host(HostName("test-host"))

    # Initially no tags
    tags = docker_provider.get_host_tags(host)
    assert tags == {}

    # Add tags
    docker_provider.add_tags_to_host(host, {"env": "test", "team": "backend"})
    tags = docker_provider.get_host_tags(host)
    assert tags["env"] == "test"
    assert tags["team"] == "backend"

    # Remove a tag
    docker_provider.remove_tags_from_host(host, ["env"])
    tags = docker_provider.get_host_tags(host)
    assert "env" not in tags
    assert tags["team"] == "backend"


@pytest.mark.timeout(180)
def test_mngr_create_echo_command_on_docker(temp_source_dir: Path, docker_test_id: str) -> None:
    """Test creating an agent with echo command on Docker using the CLI.

    This is an end-to-end integration test that verifies the full flow:
    1. CLI parses arguments correctly
    2. Docker container is created
    3. SSH connection is established
    4. Work directory is copied to remote host
    5. Agent is created and command runs
    """
    agent_name = f"test-docker-echo-{docker_test_id}"
    expected_output = f"hello-from-docker-{docker_test_id}"

    try:
        result = subprocess.run(
            [
                "uv",
                "run",
                "mngr",
                "create",
                agent_name,
                "echo",
                "--in",
                "docker",
                "--no-connect",
                "--await-ready",
                "--no-ensure-clean",
                "--source",
                str(temp_source_dir),
                "--",
                expected_output,
            ],
            capture_output=True,
            text=True,
            timeout=180,
        )

        assert result.returncode == 0, f"CLI failed with stderr: {result.stderr}\nstdout: {result.stdout}"
        assert "Created agent:" in result.stdout, f"Expected 'Created agent:' in output: {result.stdout}"
    finally:
        # Clean up the agent/container
        subprocess.run(
            ["uv", "run", "mngr", "destroy", agent_name, "-y"],
            capture_output=True,
            timeout=60,
        )
