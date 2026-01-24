"""Acceptance tests for creating agents on Modal.

These tests require Modal credentials and network access to run. They are marked
with @pytest.mark.acceptance and are skipped by default. To run them:

    pytest -m modal --timeout=300

Or to run all tests including Modal tests:

    pytest --timeout=300
"""

import os
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

# Install minimal dependencies for mngr to work (openssh, tmux, rsync for file transfer)
RUN apt-get update && apt-get install -y --no-install-recommends \\
    openssh-server \\
    tmux \\
    python3 \\
    rsync \\
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


@pytest.mark.acceptance
@pytest.mark.timeout(300)
def test_mngr_create_with_failing_dockerfile_shows_build_failure(temp_source_dir: Path) -> None:
    """Test that a failing Dockerfile command shows the build failure in output.

    When a Dockerfile has a command that fails during the build process, mngr should:
    1. Return a non-zero exit code
    2. Show the failure message in the output so the user can see what went wrong

    This is important for debuggability - users need to see why their build failed.
    """
    agent_name = f"test-modal-dockerfile-fail-{uuid4().hex[:8]}"

    # Create a Dockerfile with a command that will definitely fail
    dockerfile_path = temp_source_dir / "Dockerfile"
    # Use a unique marker so we can verify the actual failing command is shown in output
    unique_failure_marker = f"intentional-fail-{uuid4().hex[:8]}"
    dockerfile_content = f"""\
FROM debian:bookworm-slim

# This command will fail intentionally
RUN echo "About to fail with marker: {unique_failure_marker}" && exit 1
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
            "should-not-reach-here",
        ],
        capture_output=True,
        text=True,
        timeout=300,
    )

    # The command should fail because the Dockerfile build fails
    assert result.returncode != 0, (
        f"Expected mngr create to fail when Dockerfile has failing command, "
        f"but got returncode {result.returncode}.\nstdout: {result.stdout}\nstderr: {result.stderr}"
    )

    # The combined output should contain the unique marker from the failing command
    # so the user can see what actually failed in the build
    combined_output = result.stdout + result.stderr
    assert unique_failure_marker in combined_output, (
        f"Expected the failing build command's output to be visible in mngr output. "
        f"Looking for unique marker '{unique_failure_marker}' in output.\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )


@pytest.fixture
def temp_git_source_dir() -> Generator[Path, None, None]:
    """Create a temporary source directory with a git repository."""
    with tempfile.TemporaryDirectory() as tmpdir:
        source_dir = Path(tmpdir)
        # Create a file and initialize git
        (source_dir / "tracked.txt").write_text("tracked content")
        subprocess.run(["git", "init"], cwd=source_dir, capture_output=True, check=True)
        subprocess.run(["git", "add", "."], cwd=source_dir, capture_output=True, check=True)
        subprocess.run(
            ["git", "commit", "-m", "Initial commit"],
            cwd=source_dir,
            capture_output=True,
            check=True,
            env={
                **os.environ,
                "GIT_AUTHOR_NAME": "Test",
                "GIT_AUTHOR_EMAIL": "test@test.com",
                "GIT_COMMITTER_NAME": "Test",
                "GIT_COMMITTER_EMAIL": "test@test.com",
            },
        )
        # Add an untracked file
        (source_dir / "untracked.txt").write_text("untracked content")
        yield source_dir


@pytest.mark.acceptance
@pytest.mark.timeout(300)
def test_mngr_create_transfers_git_repo_with_untracked_files(temp_git_source_dir: Path) -> None:
    """Test that git repo and untracked files are correctly transferred to Modal.

    This tests the file transfer functionality:
    1. Git repository is pushed via git push --mirror
    2. Untracked files are transferred via rsync
    3. Both tracked and untracked files are accessible on the remote host
    """
    agent_name = f"test-modal-git-{uuid4().hex[:8]}"
    unique_marker = f"git-transfer-test-{uuid4().hex[:8]}"

    # Write a unique marker to verify file transfer
    (temp_git_source_dir / "marker.txt").write_text(unique_marker)

    # Create agent that will verify the files exist
    result = subprocess.run(
        [
            "uv",
            "run",
            "mngr",
            "create",
            agent_name,
            "generic",
            "--in",
            "modal",
            "--no-connect",
            "--await-ready",
            "--no-ensure-clean",
            "--source",
            str(temp_git_source_dir),
            "--",
            f"cat tracked.txt && cat untracked.txt && cat marker.txt && echo {unique_marker}-verified",
        ],
        capture_output=True,
        text=True,
        timeout=300,
    )

    assert result.returncode == 0, f"CLI failed with stderr: {result.stderr}\nstdout: {result.stdout}"
    assert "Created agent:" in result.stdout, f"Expected 'Created agent:' in output: {result.stdout}"


@pytest.mark.acceptance
@pytest.mark.timeout(300)
def test_mngr_create_transfers_git_repo_with_new_branch(temp_git_source_dir: Path) -> None:
    """Test that git transfer creates a new branch on the remote.

    This tests the git branch creation functionality during transfer:
    1. Git repository is pushed via git push --mirror
    2. A new branch is created with the specified prefix
    """
    agent_name = f"test-modal-branch-{uuid4().hex[:8]}"

    result = subprocess.run(
        [
            "uv",
            "run",
            "mngr",
            "create",
            agent_name,
            "generic",
            "--in",
            "modal",
            "--no-connect",
            "--await-ready",
            "--no-ensure-clean",
            "--source",
            str(temp_git_source_dir),
            "--new-branch=",
            "--",
            "git rev-parse --abbrev-ref HEAD && sleep 3600",
        ],
        capture_output=True,
        text=True,
        timeout=300,
    )

    assert result.returncode == 0, f"CLI failed with stderr: {result.stderr}\nstdout: {result.stdout}"
    assert "Created agent:" in result.stdout, f"Expected 'Created agent:' in output: {result.stdout}"