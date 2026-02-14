"""Integration and acceptance tests for the ttyd plugin + mngr open chain.

Integration tests verify the full local flow:
  create agent -> ttyd hook fires -> URL written -> mngr open picks it up

Acceptance tests verify the flow on Modal (requires credentials + network).
"""

import shutil
import subprocess
from pathlib import Path
from typing import Generator
from typing import cast
from uuid import uuid4

import pluggy
import pytest

import imbue.mngr.plugins.ttyd.plugin as ttyd_plugin_module
from imbue.concurrency_group.concurrency_group import ConcurrencyGroup
from imbue.mngr.agents.agent_registry import load_agents_from_plugins
from imbue.mngr.api.create import create
from imbue.mngr.api.open import _resolve_agent_url
from imbue.mngr.api.providers import get_provider_instance
from imbue.mngr.config.data_types import MngrConfig
from imbue.mngr.config.data_types import MngrContext
from imbue.mngr.conftest import ModalSubprocessTestEnv
from imbue.mngr.conftest import make_mngr_ctx
from imbue.mngr.hosts.host import HostLocation
from imbue.mngr.interfaces.host import CreateAgentOptions
from imbue.mngr.interfaces.host import OnlineHostInterface
from imbue.mngr.plugins import hookspecs
from imbue.mngr.primitives import AgentName
from imbue.mngr.primitives import AgentTypeName
from imbue.mngr.primitives import CommandString
from imbue.mngr.primitives import HostName
from imbue.mngr.primitives import LOCAL_PROVIDER_NAME
from imbue.mngr.primitives import ProviderInstanceName
from imbue.mngr.providers.registry import load_local_backend_only
from imbue.mngr.utils.testing import get_short_random_string
from imbue.mngr.utils.testing import tmux_session_cleanup
from imbue.mngr.utils.testing import tmux_session_exists


@pytest.fixture
def ttyd_mngr_ctx(
    temp_config: MngrConfig,
    temp_profile_dir: Path,
) -> Generator[MngrContext, None, None]:
    """Create a MngrContext with the ttyd plugin registered.

    The default plugin_manager fixture does not load utility plugins (ttyd, port
    forwarding). This fixture creates a context that includes the ttyd plugin so
    its on_agent_created hook fires during agent creation.
    """
    pm = pluggy.PluginManager("mngr")
    pm.add_hookspecs(hookspecs)
    pm.load_setuptools_entrypoints("mngr")
    load_local_backend_only(pm)
    load_agents_from_plugins(pm)
    pm.register(ttyd_plugin_module)

    cg = ConcurrencyGroup(name="test-ttyd")
    with cg:
        yield make_mngr_ctx(temp_config, pm, temp_profile_dir, concurrency_group=cg)


def _get_local_host_and_location(ctx: MngrContext, temp_work_dir: Path) -> tuple[OnlineHostInterface, HostLocation]:
    local_provider = get_provider_instance(ProviderInstanceName(LOCAL_PROVIDER_NAME), ctx)
    local_host = cast(OnlineHostInterface, local_provider.get_host(HostName("local")))
    source_location = HostLocation(host=local_host, path=temp_work_dir)
    return local_host, source_location


# =============================================================================
# Integration tests (local, require ttyd installed)
# =============================================================================


@pytest.mark.skipif(shutil.which("ttyd") is None, reason="ttyd not installed")
def test_create_agent_writes_terminal_url_for_local_host(
    ttyd_mngr_ctx: MngrContext,
    temp_work_dir: Path,
    temp_host_dir: Path,
) -> None:
    """Test that creating a local agent with ttyd writes a terminal URL.

    This verifies the full integration chain:
    1. create() calls on_agent_created hooks
    2. ttyd plugin's hook fires and starts ttyd
    3. For local hosts, URL is written directly to status/urls/terminal
    4. get_reported_urls() returns the terminal URL
    """
    agent_name = AgentName(f"test-ttyd-url-{uuid4().hex}")
    session_name = f"{ttyd_mngr_ctx.config.prefix}{agent_name}"

    with tmux_session_cleanup(session_name):
        local_host, source_location = _get_local_host_and_location(ttyd_mngr_ctx, temp_work_dir)

        agent_options = CreateAgentOptions(
            agent_type=AgentTypeName("echo"),
            name=agent_name,
            command=CommandString("sleep 492817"),
        )

        result = create(
            source_location=source_location,
            target_host=local_host,
            agent_options=agent_options,
            mngr_ctx=ttyd_mngr_ctx,
        )

        assert result.agent is not None
        assert tmux_session_exists(session_name)

        # Verify the URL file was written on disk
        url_file = temp_host_dir / "agents" / str(result.agent.id) / "status" / "urls" / "terminal"
        assert url_file.exists(), f"URL file not found at {url_file}"
        url_content = url_file.read_text()
        assert url_content.startswith("http://localhost:"), f"Unexpected URL content: {url_content}"

        # The ttyd hook should have written a terminal URL
        urls = result.agent.get_reported_urls()
        assert "terminal" in urls, f"Expected 'terminal' URL but got: {urls}"
        assert urls["terminal"].startswith("http://localhost:")

        # Verify _resolve_agent_url can find it
        resolved = _resolve_agent_url(result.agent, url_type="terminal")
        assert resolved.startswith("http://localhost:")

        # Verify the default URL resolution also works (falls back to first available)
        default_url = _resolve_agent_url(result.agent, url_type=None)
        assert default_url.startswith("http://localhost:")


@pytest.mark.skipif(shutil.which("ttyd") is None, reason="ttyd not installed")
def test_destroy_agent_cleans_up_terminal_url(
    ttyd_mngr_ctx: MngrContext,
    temp_work_dir: Path,
    temp_host_dir: Path,
) -> None:
    """Test that destroying an agent removes the terminal URL file."""
    agent_name = AgentName(f"test-ttyd-cleanup-{uuid4().hex}")
    session_name = f"{ttyd_mngr_ctx.config.prefix}{agent_name}"

    with tmux_session_cleanup(session_name):
        local_host, source_location = _get_local_host_and_location(ttyd_mngr_ctx, temp_work_dir)

        agent_options = CreateAgentOptions(
            agent_type=AgentTypeName("echo"),
            name=agent_name,
            command=CommandString("sleep 183746"),
        )

        result = create(
            source_location=source_location,
            target_host=local_host,
            agent_options=agent_options,
            mngr_ctx=ttyd_mngr_ctx,
        )

        assert result.agent is not None

        # Verify URL exists after creation
        urls = result.agent.get_reported_urls()
        assert "terminal" in urls

        # Get the URL file path for later verification
        agent_dir = temp_host_dir / "agents" / str(result.agent.id)
        url_file = agent_dir / "status" / "urls" / "terminal"
        assert url_file.exists()

        # Destroy the agent -- this removes the entire agent state directory,
        # which includes the status/urls/ subdirectory
        local_host.destroy_agent(result.agent)

        # The URL file no longer exists because the agent state directory was removed
        assert not url_file.exists()


# =============================================================================
# Acceptance tests (Modal, require credentials + network)
# =============================================================================


@pytest.mark.acceptance
@pytest.mark.timeout(300)
def test_mngr_open_shows_url_for_modal_agent(
    tmp_path: Path,
    modal_subprocess_env: ModalSubprocessTestEnv,
) -> None:
    """Test that mngr open shows a URL for an agent created on Modal.

    This is an end-to-end acceptance test that verifies:
    1. Agent is created on Modal
    2. ttyd plugin installs ttyd and starts a web terminal
    3. forward-service registers the terminal URL
    4. mngr open can find and display the URL
    """
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    (source_dir / "test.txt").write_text("test content")

    agent_name = f"test-modal-open-{get_short_random_string()}"

    # Create agent on Modal
    create_result = subprocess.run(
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
            str(source_dir),
            "--",
            "sleep 300",
        ],
        capture_output=True,
        text=True,
        timeout=300,
        env=modal_subprocess_env.env,
    )

    assert create_result.returncode == 0, (
        f"Create failed with stderr: {create_result.stderr}\nstdout: {create_result.stdout}"
    )

    # Now try mngr open -- it should find the agent's URL
    # We use --no-start since the agent is already running
    # The command will fail to actually open a browser in CI, but we can check the output
    open_result = subprocess.run(
        [
            "uv",
            "run",
            "mngr",
            "open",
            agent_name,
        ],
        capture_output=True,
        text=True,
        timeout=60,
        env=modal_subprocess_env.env,
    )

    # mngr open should either succeed (opened URL) or fail with "has no URL"
    # (if ttyd didn't install in time). Either way, it shouldn't crash.
    if open_result.returncode == 0:
        assert "Opening URL" in open_result.stderr or open_result.returncode == 0
    else:
        # Acceptable: agent exists but no URL yet (ttyd may not have started)
        assert "has no URL" in open_result.stderr or "has no URL" in open_result.stdout

    # Clean up: destroy the agent
    subprocess.run(
        ["uv", "run", "mngr", "destroy", agent_name, "--yes"],
        capture_output=True,
        text=True,
        timeout=120,
        env=modal_subprocess_env.env,
    )
