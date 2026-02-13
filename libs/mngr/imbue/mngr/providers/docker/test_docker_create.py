"""Acceptance and release tests for Docker provider via CLI.

End-to-end tests that use the mngr CLI as a subprocess, verifying the full
user-facing flow. Requires a running Docker daemon.

To run these tests:
    just test libs/mngr/imbue/mngr/providers/docker/test_docker_create.py
"""

import subprocess
from pathlib import Path

import pytest

from imbue.mngr.utils.testing import get_short_random_string
from imbue.mngr.utils.testing import get_subprocess_test_env


@pytest.fixture
def docker_subprocess_env(tmp_path: Path) -> dict[str, str]:
    """Create a subprocess test environment for Docker tests."""
    host_dir = tmp_path / "docker-test-hosts"
    host_dir.mkdir()
    return get_subprocess_test_env(
        root_name="mngr-docker-test",
        host_dir=host_dir,
    )


@pytest.fixture
def temp_source_dir(tmp_path: Path) -> Path:
    """Create a temporary source directory for tests."""
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    (source_dir / "test.txt").write_text("test content")
    return source_dir


@pytest.mark.acceptance
@pytest.mark.timeout(120)
def test_mngr_create_echo_command_on_docker(
    temp_source_dir: Path,
    docker_subprocess_env: dict[str, str],
) -> None:
    """Test creating an agent with echo command on Docker using the CLI."""
    agent_name = f"test-docker-echo-{get_short_random_string()}"
    expected_output = f"hello-from-docker-{get_short_random_string()}"

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
        timeout=120,
        env=docker_subprocess_env,
    )

    assert result.returncode == 0, f"CLI failed with stderr: {result.stderr}\nstdout: {result.stdout}"
    assert "Done." in result.stdout, f"Expected 'Done.' in output: {result.stdout}"


@pytest.mark.acceptance
@pytest.mark.timeout(120)
def test_mngr_create_with_build_args_on_docker(
    temp_source_dir: Path,
    docker_subprocess_env: dict[str, str],
) -> None:
    """Test creating a Docker host with custom CPU and memory build args."""
    agent_name = f"test-docker-build-{get_short_random_string()}"
    expected_output = f"build-test-{get_short_random_string()}"

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
            "-b",
            "--cpu",
            "-b",
            "2",
            "-b",
            "--memory",
            "-b",
            "2",
            "--",
            expected_output,
        ],
        capture_output=True,
        text=True,
        timeout=120,
        env=docker_subprocess_env,
    )

    assert result.returncode == 0, f"CLI failed with stderr: {result.stderr}\nstdout: {result.stdout}"
    assert "Done." in result.stdout, f"Expected 'Done.' in output: {result.stdout}"


@pytest.mark.acceptance
@pytest.mark.timeout(120)
def test_mngr_create_with_tags_on_docker(
    temp_source_dir: Path,
    docker_subprocess_env: dict[str, str],
) -> None:
    """Test creating a Docker host with tags and verify they appear."""
    agent_name = f"test-docker-tags-{get_short_random_string()}"
    expected_output = f"tags-test-{get_short_random_string()}"

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
            "--tag",
            "env=test",
            "--",
            expected_output,
        ],
        capture_output=True,
        text=True,
        timeout=120,
        env=docker_subprocess_env,
    )

    assert result.returncode == 0, f"CLI failed with stderr: {result.stderr}\nstdout: {result.stdout}"
    assert "Done." in result.stdout, f"Expected 'Done.' in output: {result.stdout}"


@pytest.mark.acceptance
@pytest.mark.timeout(120)
def test_mngr_create_with_dockerfile_on_docker(
    temp_source_dir: Path,
    docker_subprocess_env: dict[str, str],
) -> None:
    """Test creating a Docker host using a custom Dockerfile."""
    agent_name = f"test-docker-df-{get_short_random_string()}"
    expected_output = f"dockerfile-test-{get_short_random_string()}"

    dockerfile_path = temp_source_dir / "Dockerfile"
    dockerfile_content = """\
FROM debian:bookworm-slim

RUN apt-get update && apt-get install -y --no-install-recommends \\
    openssh-server \\
    tmux \\
    python3 \\
    rsync \\
    && rm -rf /var/lib/apt/lists/*

RUN echo "custom-dockerfile-marker" > /dockerfile-marker.txt
"""
    dockerfile_path.write_text(dockerfile_content)

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
            "-b",
            f"--dockerfile={dockerfile_path}",
            "--",
            expected_output,
        ],
        capture_output=True,
        text=True,
        timeout=120,
        env=docker_subprocess_env,
    )

    assert result.returncode == 0, f"CLI failed with stderr: {result.stderr}\nstdout: {result.stdout}"
    assert "Done." in result.stdout, f"Expected 'Done.' in output: {result.stdout}"


@pytest.mark.release
@pytest.mark.timeout(180)
def test_mngr_create_stop_start_destroy_lifecycle(
    temp_source_dir: Path,
    docker_subprocess_env: dict[str, str],
) -> None:
    """Full lifecycle test: create, stop, start, destroy via CLI."""
    agent_name = f"test-docker-lifecycle-{get_short_random_string()}"

    # Create
    create_result = subprocess.run(
        [
            "uv",
            "run",
            "mngr",
            "create",
            agent_name,
            "generic",
            "--in",
            "docker",
            "--no-connect",
            "--await-ready",
            "--no-ensure-clean",
            "--source",
            str(temp_source_dir),
            "--",
            "sleep 3600",
        ],
        capture_output=True,
        text=True,
        timeout=180,
        env=docker_subprocess_env,
    )
    assert create_result.returncode == 0, (
        f"Create failed with stderr: {create_result.stderr}\nstdout: {create_result.stdout}"
    )

    # Stop
    stop_result = subprocess.run(
        [
            "uv",
            "run",
            "mngr",
            "stop",
            agent_name,
        ],
        capture_output=True,
        text=True,
        timeout=60,
        env=docker_subprocess_env,
    )
    assert stop_result.returncode == 0, (
        f"Stop failed with stderr: {stop_result.stderr}\nstdout: {stop_result.stdout}"
    )

    # Start
    start_result = subprocess.run(
        [
            "uv",
            "run",
            "mngr",
            "start",
            agent_name,
            "--no-connect",
        ],
        capture_output=True,
        text=True,
        timeout=120,
        env=docker_subprocess_env,
    )
    assert start_result.returncode == 0, (
        f"Start failed with stderr: {start_result.stderr}\nstdout: {start_result.stdout}"
    )

    # Destroy
    destroy_result = subprocess.run(
        [
            "uv",
            "run",
            "mngr",
            "destroy",
            agent_name,
            "--yes",
        ],
        capture_output=True,
        text=True,
        timeout=60,
        env=docker_subprocess_env,
    )
    assert destroy_result.returncode == 0, (
        f"Destroy failed with stderr: {destroy_result.stderr}\nstdout: {destroy_result.stdout}"
    )
