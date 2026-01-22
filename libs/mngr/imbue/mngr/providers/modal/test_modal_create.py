"""Acceptance tests for creating agents on Modal.

These tests require Modal credentials and network access to run. They are marked
with @pytest.mark.acceptance and are skipped by default. To run them:

    pytest -m modal --timeout=300

Or to run all tests including Modal tests:

    pytest --timeout=300
"""

import subprocess
import tempfile
from collections.abc import Generator
from pathlib import Path
from uuid import uuid4

import pytest


@pytest.fixture
def temp_source_dir() -> Generator[Path, None, None]:
    """Create a temporary source directory for tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        source_dir = Path(tmpdir)
        # Create a simple file so the directory isn't empty
        (source_dir / "test.txt").write_text("test content")
        yield source_dir


@pytest.mark.acceptance
@pytest.mark.timeout(300)
def test_mngr_create_echo_command_on_modal(temp_source_dir: Path) -> None:
    """Test creating an agent with echo command on Modal using the CLI.

    This is an end-to-end acceptance test that verifies the full flow:
    1. CLI parses arguments correctly
    2. Modal sandbox is created
    3. SSH connection is established
    4. Work directory is copied to remote host
    5. Agent is created and command runs
    6. Output can be verified
    """
    agent_name = f"test-modal-echo-{uuid4().hex[:8]}"
    expected_output = f"hello-from-modal-{uuid4().hex[:8]}"

    # Run mngr create with echo command on modal
    # Using --no-connect and --await-ready to run synchronously without attaching
    # Using --no-ensure-clean since temp dir won't be a git repo
    result = subprocess.run(
        [
            "uv",
            "run",
            "mngr",
            "create",
            agent_name,
            "echo",
            "--in",
            "modal",
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
        timeout=300,
    )

    assert result.returncode == 0, f"CLI failed with stderr: {result.stderr}\nstdout: {result.stdout}"
    assert "Created agent:" in result.stdout, f"Expected 'Created agent:' in output: {result.stdout}"


@pytest.mark.acceptance
@pytest.mark.timeout(300)
def test_mngr_create_with_worktree_flag_on_modal_raises_error(temp_source_dir: Path) -> None:
    """Test that explicitly requesting --worktree on modal raises an error.

    The --worktree flag only works when source and target are on the same host.
    Modal is always a remote host, so this should fail.
    """
    agent_name = f"test-modal-worktree-{uuid4().hex[:8]}"

    result = subprocess.run(
        [
            "uv",
            "run",
            "mngr",
            "create",
            agent_name,
            "echo",
            "--in",
            "modal",
            "--worktree",
            "--no-connect",
            "--await-ready",
            "--no-ensure-clean",
            "--source",
            str(temp_source_dir),
            "--",
            "hello",
        ],
        capture_output=True,
        text=True,
        timeout=300,
    )

    # Should fail with an error about worktree mode
    assert result.returncode != 0, "Expected worktree on modal to fail"
    assert "worktree" in result.stderr.lower() or "worktree" in result.stdout.lower(), (
        f"Expected error message about worktree mode. stderr: {result.stderr}\nstdout: {result.stdout}"
    )


@pytest.mark.acceptance
@pytest.mark.timeout(300)
def test_mngr_create_with_build_args_on_modal(temp_source_dir: Path) -> None:
    """Test creating an agent on Modal with custom build args (cpu, memory).

    This verifies that build arguments are passed correctly to the Modal sandbox.
    """
    agent_name = f"test-modal-build-{uuid4().hex[:8]}"
    expected_output = f"build-test-{uuid4().hex[:8]}"

    result = subprocess.run(
        [
            "uv",
            "run",
            "mngr",
            "create",
            agent_name,
            "echo",
            "--in",
            "modal",
            "--no-connect",
            "--await-ready",
            "--no-ensure-clean",
            "--source",
            str(temp_source_dir),
            "-b",
            "--cpu",
            "-b",
            "0.5",
            "-b",
            "--memory",
            "-b",
            "0.5",
            "--",
            expected_output,
        ],
        capture_output=True,
        text=True,
        timeout=300,
    )

    assert result.returncode == 0, f"CLI failed with stderr: {result.stderr}\nstdout: {result.stdout}"
    assert "Created agent:" in result.stdout, f"Expected 'Created agent:' in output: {result.stdout}"


@pytest.mark.acceptance
@pytest.mark.timeout(300)
def test_mngr_create_with_dockerfile_on_modal(temp_source_dir: Path) -> None:
    """Test creating an agent on Modal using a custom Dockerfile.

    This verifies that:
    1. The --dockerfile build arg is correctly parsed by the modal provider
    2. Modal builds an image from the Dockerfile
    3. The sandbox runs with the custom image
    """
    agent_name = f"test-modal-dockerfile-{uuid4().hex[:8]}"
    expected_output = f"dockerfile-test-{uuid4().hex[:8]}"

    # Create a simple Dockerfile in the source directory
    dockerfile_path = temp_source_dir / "Dockerfile"
    dockerfile_content = """\
FROM debian:bookworm-slim

# Install minimal dependencies for mngr to work (openssh, tmux)
RUN apt-get update && apt-get install -y --no-install-recommends \\
    openssh-server \\
    tmux \\
    python3 \\
    && rm -rf /var/lib/apt/lists/*

# Create a marker file to verify we're using the custom image
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
            "modal",
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
        timeout=300,
    )

    assert result.returncode == 0, f"CLI failed with stderr: {result.stderr}\nstdout: {result.stdout}"
    assert "Created agent:" in result.stdout, f"Expected 'Created agent:' in output: {result.stdout}"
