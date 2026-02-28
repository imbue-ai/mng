import os
import shutil
import stat
import subprocess
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

import pytest

import imbue.imbue_common.resource_guards as rg
from imbue.imbue_common.resource_guards import cleanup_resource_guard_wrappers
from imbue.imbue_common.resource_guards import create_resource_guard_wrappers
from imbue.imbue_common.resource_guards import generate_wrapper_script

# Use ubiquitous coreutils binaries so these tests run on any system.
_TEST_RESOURCES = ["echo", "cat", "ls"]


@contextmanager
def _isolated_guard_state() -> Generator[None, None, None]:
    """Save and restore resource guard module state and env vars."""
    original_dir = rg._guard_wrapper_dir
    original_owns = rg._owns_guard_wrapper_dir
    original_patcher = rg._session_env_patcher
    original_resources = rg._guarded_resources
    saved_env = {k: os.environ.pop(k, None) for k in ("_PYTEST_GUARD_WRAPPER_DIR",)}
    try:
        yield
    finally:
        if rg._session_env_patcher is not None and rg._session_env_patcher is not original_patcher:
            rg._session_env_patcher.stop()
        rg._guard_wrapper_dir = original_dir
        rg._owns_guard_wrapper_dir = original_owns
        rg._session_env_patcher = original_patcher
        rg._guarded_resources = original_resources
        for k, v in saved_env.items():
            if v is not None:
                os.environ[k] = v
            else:
                os.environ.pop(k, None)


@pytest.fixture()
def wrapper(tmp_path: Path) -> Path:
    """Create a guard wrapper for a fake resource backed by /usr/bin/true."""
    real_true = shutil.which("true")
    assert real_true is not None
    path = tmp_path / "fakecmd"
    path.write_text(generate_wrapper_script("fakecmd", real_true))
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


def _run_wrapper(
    wrapper: Path,
    *,
    guard: str,
    tracking_dir: Path | None = None,
    in_call_phase: bool = True,
) -> subprocess.CompletedProcess[str]:
    """Run a wrapper script with the given guard setting."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("_PYTEST_GUARD")}
    if in_call_phase:
        env["_PYTEST_GUARD_PHASE"] = "call"
        env["_PYTEST_GUARD_FAKECMD"] = guard
        if tracking_dir is not None:
            env["_PYTEST_GUARD_TRACKING_DIR"] = str(tracking_dir)
    return subprocess.run([str(wrapper)], env=env, capture_output=True, text=True)


# ---------------------------------------------------------------------------
# Script generation
# ---------------------------------------------------------------------------


def test_generate_wrapper_script_contains_shebang_and_exec() -> None:
    script = generate_wrapper_script("mybin", "/usr/bin/mybin")
    assert script.startswith("#!/bin/bash\n")
    assert 'exec "/usr/bin/mybin" "$@"' in script


def test_generate_wrapper_script_contains_guard_check() -> None:
    script = generate_wrapper_script("mybin", "/usr/bin/mybin")
    assert "$_PYTEST_GUARD_MYBIN" in script
    assert "@pytest.mark.mybin" in script
    assert '"block"' in script
    assert '"allow"' in script


# ---------------------------------------------------------------------------
# Wrapper behavior
# ---------------------------------------------------------------------------


def test_wrapper_blocks_unmarked_invocation(wrapper: Path) -> None:
    """guard=block should exit 127 and print an error."""
    result = _run_wrapper(wrapper, guard="block")
    assert result.returncode == 127
    assert "RESOURCE GUARD" in result.stderr


def test_wrapper_blocked_invocation_creates_tracking_file(wrapper: Path, tmp_path: Path) -> None:
    """guard=block should create a blocked_<resource> tracking file."""
    tracking_dir = tmp_path / "tracking"
    tracking_dir.mkdir()
    _run_wrapper(wrapper, guard="block", tracking_dir=tracking_dir)
    assert (tracking_dir / "blocked_fakecmd").exists()


def test_wrapper_allows_marked_invocation(wrapper: Path, tmp_path: Path) -> None:
    """guard=allow should delegate and create a tracking file."""
    tracking_dir = tmp_path / "tracking"
    tracking_dir.mkdir()
    result = _run_wrapper(wrapper, guard="allow", tracking_dir=tracking_dir)
    assert result.returncode == 0
    assert (tracking_dir / "fakecmd").exists()


def test_wrapper_passes_through_outside_call_phase(wrapper: Path) -> None:
    """Without _PYTEST_GUARD_PHASE=call, the wrapper should always delegate."""
    result = _run_wrapper(wrapper, guard="block", in_call_phase=False)
    assert result.returncode == 0


# ---------------------------------------------------------------------------
# Session lifecycle
# ---------------------------------------------------------------------------


def test_create_and_cleanup_round_trip() -> None:
    """create_resource_guard_wrappers modifies PATH; cleanup restores it."""
    with _isolated_guard_state():
        create_resource_guard_wrappers(_TEST_RESOURCES)

        assert rg._guard_wrapper_dir is not None
        wrapper_dir = rg._guard_wrapper_dir
        assert os.environ["PATH"].startswith(wrapper_dir)

        for resource in _TEST_RESOURCES:
            assert (Path(wrapper_dir) / resource).exists()

        cleanup_resource_guard_wrappers()
        assert rg._guard_wrapper_dir is None
        assert not Path(wrapper_dir).exists()
        assert not os.environ["PATH"].startswith(wrapper_dir)
