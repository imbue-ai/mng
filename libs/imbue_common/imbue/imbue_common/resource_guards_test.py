import os
import shutil
import stat
import subprocess
from pathlib import Path

from imbue.imbue_common.resource_guards import GUARDED_RESOURCES
from imbue.imbue_common.resource_guards import cleanup_resource_guard_wrappers
from imbue.imbue_common.resource_guards import create_resource_guard_wrappers
from imbue.imbue_common.resource_guards import generate_wrapper_script


def test_generate_wrapper_script_contains_shebang_and_exec() -> None:
    script = generate_wrapper_script("tmux", "/usr/bin/tmux")
    assert script.startswith("#!/bin/bash\n")
    assert 'exec "/usr/bin/tmux" "$@"' in script


def test_generate_wrapper_script_contains_guard_check() -> None:
    script = generate_wrapper_script("rsync", "/usr/bin/rsync")
    assert "$_PYTEST_GUARD_RSYNC" in script
    assert "@pytest.mark.rsync" in script
    assert '"block"' in script
    assert '"allow"' in script


def test_wrapper_blocks_unmarked_invocation(tmp_path: Path) -> None:
    """A wrapper with guard=block should exit 127 and print an error."""
    real_true = shutil.which("true")
    assert real_true is not None

    wrapper = tmp_path / "fakecmd"
    wrapper.write_text(generate_wrapper_script("fakecmd", real_true))
    wrapper.chmod(wrapper.stat().st_mode | stat.S_IXUSR)

    env = {
        **os.environ,
        "_PYTEST_GUARD_PHASE": "call",
        "_PYTEST_GUARD_FAKECMD": "block",
    }
    result = subprocess.run(
        [str(wrapper)],
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 127
    assert "RESOURCE GUARD" in result.stderr


def test_wrapper_allows_marked_invocation(tmp_path: Path) -> None:
    """A wrapper with guard=allow should delegate and create a tracking file."""
    real_true = shutil.which("true")
    assert real_true is not None

    tracking_dir = tmp_path / "tracking"
    tracking_dir.mkdir()

    wrapper = tmp_path / "fakecmd"
    wrapper.write_text(generate_wrapper_script("fakecmd", real_true))
    wrapper.chmod(wrapper.stat().st_mode | stat.S_IXUSR)

    env = {
        **os.environ,
        "_PYTEST_GUARD_PHASE": "call",
        "_PYTEST_GUARD_FAKECMD": "allow",
        "_PYTEST_GUARD_TRACKING_DIR": str(tracking_dir),
    }
    result = subprocess.run(
        [str(wrapper)],
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert (tracking_dir / "fakecmd").exists()


def test_wrapper_passes_through_outside_call_phase(tmp_path: Path) -> None:
    """Without _PYTEST_GUARD_PHASE=call, the wrapper should always delegate."""
    real_true = shutil.which("true")
    assert real_true is not None

    wrapper = tmp_path / "fakecmd"
    wrapper.write_text(generate_wrapper_script("fakecmd", real_true))
    wrapper.chmod(wrapper.stat().st_mode | stat.S_IXUSR)

    # No _PYTEST_GUARD_PHASE in environment
    env = {k: v for k, v in os.environ.items() if not k.startswith("_PYTEST_GUARD")}
    result = subprocess.run(
        [str(wrapper)],
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0


def test_create_and_cleanup_round_trip() -> None:
    """create_resource_guard_wrappers modifies PATH; cleanup restores it."""
    import imbue.imbue_common.resource_guards as rg

    # Save original module state
    original_dir = rg._guard_wrapper_dir
    original_owns = rg._owns_guard_wrapper_dir
    original_path = os.environ.get("PATH", "")

    # Clear any pre-existing guard env vars so create sees a fresh state
    for key in ("_PYTEST_GUARD_WRAPPER_DIR", "_PYTEST_GUARD_ORIGINAL_PATH"):
        os.environ.pop(key, None)

    try:
        create_resource_guard_wrappers()

        # Wrapper dir should be set and prepended to PATH
        assert rg._guard_wrapper_dir is not None
        wrapper_dir = rg._guard_wrapper_dir
        assert os.environ["PATH"].startswith(wrapper_dir)

        # Each guarded resource should have a wrapper script
        for resource in GUARDED_RESOURCES:
            wrapper = Path(wrapper_dir) / resource
            assert wrapper.exists()
            assert wrapper.stat().st_mode & stat.S_IXUSR

        # Cleanup should restore PATH and remove the directory
        cleanup_resource_guard_wrappers()
        assert rg._guard_wrapper_dir is None
        assert not Path(wrapper_dir).exists()
        assert not os.environ["PATH"].startswith(wrapper_dir)
    finally:
        # Restore original state no matter what
        rg._guard_wrapper_dir = original_dir
        rg._owns_guard_wrapper_dir = original_owns
        os.environ["PATH"] = original_path
        for key in ("_PYTEST_GUARD_WRAPPER_DIR", "_PYTEST_GUARD_ORIGINAL_PATH"):
            os.environ.pop(key, None)
