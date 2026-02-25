import shutil
import subprocess
from pathlib import Path

import pytest

from imbue.mng.utils.polling import wait_for
from imbue.mng.utils.testing import capture_tmux_pane_contents
from imbue.mng.utils.testing import get_short_random_string
from imbue.mng.utils.testing import get_subprocess_test_env
from imbue.mng.utils.testing import mng_agent_cleanup
from imbue.mng.utils.testing import run_mng_subprocess
from imbue.mng.utils.testing import tmux_session_exists


def _create_opencode_agent(
    name: str,
    source_dir: Path,
    env: dict[str, str],
) -> subprocess.CompletedProcess[str]:
    """Create an opencode agent with standard test flags."""
    return run_mng_subprocess(
        "create",
        name,
        "opencode",
        "--no-connect",
        "--await-ready",
        "--no-ensure-clean",
        "--pass-env",
        "HOME",
        "--disable-plugin",
        "modal",
        env=env,
        cwd=source_dir,
    )


@pytest.mark.acceptance
@pytest.mark.timeout(120)
def test_opencode_agent_create_and_destroy(
    temp_git_repo: Path,
    mng_test_prefix: str,
) -> None:
    """Smoke test: create an opencode agent, verify it starts, then destroy it."""
    assert shutil.which("opencode") is not None, (
        "opencode binary not found on PATH. Install opencode to run this test."
    )

    agent_name = f"test-opencode-{get_short_random_string()}"
    session_name = f"{mng_test_prefix}{agent_name}"
    env = get_subprocess_test_env()

    with mng_agent_cleanup(agent_name, env=env, disable_plugins=["modal"]):
        result = _create_opencode_agent(agent_name, temp_git_repo, env)
        assert result.returncode == 0, (
            f"opencode agent creation failed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
        )

        assert tmux_session_exists(session_name), f"Expected tmux session {session_name} to exist"

        wait_for(
            lambda: "Ask anything" in capture_tmux_pane_contents(session_name),
            timeout=30,
            error_message="Expected opencode startup prompt 'Ask anything' to appear in tmux pane",
        )
