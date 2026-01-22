"""Integration tests for the create API.

Note: Unit tests for provider registry and configuration are in api/providers_test.py
"""

import json
import subprocess
import time
from pathlib import Path

import pluggy
import pytest

from imbue.mngr import hookimpl
from imbue.mngr.api.create import _call_on_before_create_hooks
from imbue.mngr.api.create import create
from imbue.mngr.api.data_types import NewHostOptions
from imbue.mngr.api.data_types import OnBeforeCreateArgs
from imbue.mngr.api.providers import get_provider_instance
from imbue.mngr.config.data_types import MngrContext
from imbue.mngr.errors import MngrError
from imbue.mngr.hosts.host import HostLocation
from imbue.mngr.interfaces.agent import AgentInterface
from imbue.mngr.interfaces.data_types import FileTransferSpec
from imbue.mngr.interfaces.data_types import RelativePath
from imbue.mngr.interfaces.host import AgentGitOptions
from imbue.mngr.interfaces.host import CreateAgentOptions
from imbue.mngr.interfaces.host import HostInterface
from imbue.mngr.plugins import hookspecs
from imbue.mngr.primitives import AgentName
from imbue.mngr.primitives import AgentTypeName
from imbue.mngr.primitives import CommandString
from imbue.mngr.primitives import HostName
from imbue.mngr.primitives import LOCAL_PROVIDER_NAME
from imbue.mngr.primitives import ProviderInstanceName
from imbue.mngr.primitives import WorkDirCopyMode
from imbue.mngr.utils.testing import tmux_session_cleanup
from imbue.mngr.utils.testing import tmux_session_exists

# =============================================================================
# Create API Integration Tests
# =============================================================================


def test_create_simple_echo_agent(
    temp_mngr_ctx: MngrContext,
    temp_work_dir: Path,
) -> None:
    """Test creating a simple agent that runs echo."""
    agent_name = AgentName(f"test-echo-{int(time.time())}")
    session_name = f"{temp_mngr_ctx.config.prefix}{agent_name}"

    with tmux_session_cleanup(session_name):
        local_provider = get_provider_instance(ProviderInstanceName(LOCAL_PROVIDER_NAME), temp_mngr_ctx)
        local_host = local_provider.get_host(HostName("local"))
        source_location = HostLocation(
            host=local_host,
            path=temp_work_dir,
        )

        agent_options = CreateAgentOptions(
            agent_type=AgentTypeName("echo"),
            name=agent_name,
            command=CommandString("echo 'Hello from mngr test' && sleep 365817"),
        )

        result = create(
            source_location=source_location,
            target_host=local_host,
            agent_options=agent_options,
            mngr_ctx=temp_mngr_ctx,
        )

        assert result.agent is not None
        assert result.host is not None
        assert result.agent.id is not None
        assert result.host.id is not None
        assert len(str(result.agent.id)) > 0
        assert len(str(result.host.id)) > 0
        assert tmux_session_exists(session_name), f"Expected tmux session {session_name} to exist"


def test_create_agent_with_new_host(
    temp_mngr_ctx: MngrContext,
    temp_work_dir: Path,
) -> None:
    """Test creating an agent with explicit new host options."""
    agent_name = AgentName(f"test-new-host-{int(time.time())}")
    session_name = f"{temp_mngr_ctx.config.prefix}{agent_name}"

    with tmux_session_cleanup(session_name):
        local_provider = get_provider_instance(ProviderInstanceName(LOCAL_PROVIDER_NAME), temp_mngr_ctx)
        local_host = local_provider.get_host(HostName("local"))
        source_location = HostLocation(
            host=local_host,
            path=temp_work_dir,
        )

        agent_options = CreateAgentOptions(
            agent_type=AgentTypeName("echo"),
            name=agent_name,
            command=CommandString("echo 'Created with new host' && sleep 816394"),
        )

        target_host = NewHostOptions(
            provider=LOCAL_PROVIDER_NAME,
            name=HostName("test-host"),
        )

        result = create(
            source_location=source_location,
            target_host=target_host,
            agent_options=agent_options,
            mngr_ctx=temp_mngr_ctx,
        )

        assert result.agent.id is not None
        assert result.host.id is not None
        assert tmux_session_exists(session_name)


def test_create_agent_work_dir_is_created(
    temp_mngr_ctx: MngrContext,
    temp_work_dir: Path,
) -> None:
    """Test that the agent work_dir directory is used."""
    agent_name = AgentName(f"test-work-dir-{int(time.time())}")
    session_name = f"{temp_mngr_ctx.config.prefix}{agent_name}"

    with tmux_session_cleanup(session_name):
        marker_file = temp_work_dir / "test_marker.txt"
        marker_file.write_text("work_dir marker")

        local_provider = get_provider_instance(ProviderInstanceName(LOCAL_PROVIDER_NAME), temp_mngr_ctx)
        local_host = local_provider.get_host(HostName("local"))
        source_location = HostLocation(
            host=local_host,
            path=temp_work_dir,
        )

        agent_options = CreateAgentOptions(
            agent_type=AgentTypeName("test"),
            name=agent_name,
            command=CommandString("cat test_marker.txt && sleep 30"),
        )

        result = create(
            source_location=source_location,
            target_host=local_host,
            agent_options=agent_options,
            mngr_ctx=temp_mngr_ctx,
        )

        assert result.agent.id is not None
        assert result.host.id is not None


def test_agent_state_is_persisted(
    temp_mngr_ctx: MngrContext,
    temp_work_dir: Path,
    temp_host_dir: Path,
) -> None:
    """Test that agent state is persisted to disk."""
    agent_name = AgentName(f"test-persist-{int(time.time())}")
    session_name = f"{temp_mngr_ctx.config.prefix}{agent_name}"

    with tmux_session_cleanup(session_name):
        local_provider = get_provider_instance(ProviderInstanceName(LOCAL_PROVIDER_NAME), temp_mngr_ctx)
        local_host = local_provider.get_host(HostName("local"))
        source_location = HostLocation(
            host=local_host,
            path=temp_work_dir,
        )

        agent_options = CreateAgentOptions(
            agent_type=AgentTypeName("persist-test"),
            name=agent_name,
            command=CommandString("sleep 60"),
        )

        result = create(
            source_location=source_location,
            target_host=local_host,
            agent_options=agent_options,
            mngr_ctx=temp_mngr_ctx,
        )

        agents_dir = temp_host_dir / "agents"
        assert agents_dir.exists(), "agents directory should exist"

        agent_dirs = list(agents_dir.iterdir())
        assert len(agent_dirs) > 0, "should have at least one agent directory"

        agent_dir = agents_dir / str(result.agent.id)
        data_file = agent_dir / "data.json"
        assert data_file.exists(), "agent data.json should exist"

        data = json.loads(data_file.read_text())
        assert data["id"] == str(result.agent.id)
        assert data["name"] == str(agent_name)
        assert data["type"] == "persist-test"


# =============================================================================
# Edge Cases
# =============================================================================


def test_create_agent_without_command_uses_none(
    temp_mngr_ctx: MngrContext,
    temp_work_dir: Path,
) -> None:
    """Test that creating an agent without a command is handled."""
    agent_name = AgentName(f"test-no-cmd-{int(time.time())}")
    session_name = f"{temp_mngr_ctx.config.prefix}{agent_name}"

    with tmux_session_cleanup(session_name):
        local_provider = get_provider_instance(ProviderInstanceName(LOCAL_PROVIDER_NAME), temp_mngr_ctx)
        local_host = local_provider.get_host(HostName("local"))
        source_location = HostLocation(
            host=local_host,
            path=temp_work_dir,
        )

        agent_options = CreateAgentOptions(
            agent_type=AgentTypeName("no-command"),
            name=agent_name,
        )

        result = create(
            source_location=source_location,
            target_host=local_host,
            agent_options=agent_options,
            mngr_ctx=temp_mngr_ctx,
        )

        assert result.agent.id is not None
        assert result.host.id is not None


# =============================================================================
# Worktree Tests
# =============================================================================


def test_create_agent_with_worktree(
    temp_mngr_ctx: MngrContext,
    temp_work_dir: Path,
) -> None:
    """Test creating an agent using git worktree."""
    agent_name = AgentName(f"test-worktree-{int(time.time())}")
    session_name = f"{temp_mngr_ctx.config.prefix}{agent_name}"

    subprocess.run(["git", "init"], cwd=temp_work_dir, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=temp_work_dir,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=temp_work_dir,
        check=True,
        capture_output=True,
    )
    test_file = temp_work_dir / "test.txt"
    test_file.write_text("test content")
    subprocess.run(["git", "add", "."], cwd=temp_work_dir, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "Initial commit"],
        cwd=temp_work_dir,
        check=True,
        capture_output=True,
    )

    worktree_path: Path | None = None
    with tmux_session_cleanup(session_name):
        try:
            local_provider = get_provider_instance(ProviderInstanceName(LOCAL_PROVIDER_NAME), temp_mngr_ctx)
            local_host = local_provider.get_host(HostName("local"))
            source_location = HostLocation(
                host=local_host,
                path=temp_work_dir,
            )

            agent_options = CreateAgentOptions(
                agent_type=AgentTypeName("worktree-test"),
                name=agent_name,
                command=CommandString("sleep 527146"),
                copy_mode=WorkDirCopyMode.WORKTREE,
            )

            result = create(
                source_location=source_location,
                target_host=local_host,
                agent_options=agent_options,
                mngr_ctx=temp_mngr_ctx,
            )

            assert result.agent.id is not None
            assert result.host.id is not None
            assert tmux_session_exists(session_name)

            provider = get_provider_instance(LOCAL_PROVIDER_NAME, temp_mngr_ctx)
            host = provider.get_host(result.host.id)
            agents = host.get_agents()
            agent = next((a for a in agents if a.id == result.agent.id), None)
            assert agent is not None

            worktree_path = Path(agent.work_dir)
            assert worktree_path.exists()
            assert (worktree_path / "test.txt").exists()

            result = subprocess.run(
                ["git", "branch", "--show-current"],
                cwd=worktree_path,
                capture_output=True,
                text=True,
                check=True,
            )
            branch_name = result.stdout.strip()
            assert branch_name.startswith("mngr/")
            assert str(agent_name) in branch_name
        finally:
            if worktree_path is not None:
                subprocess.run(
                    ["git", "worktree", "remove", "--force", str(worktree_path)],
                    cwd=temp_work_dir,
                    capture_output=True,
                )


def test_worktree_with_custom_branch_name(
    temp_mngr_ctx: MngrContext,
    temp_work_dir: Path,
) -> None:
    """Test creating a worktree with a custom branch name."""
    agent_name = AgentName(f"test-worktree-custom-{int(time.time())}")
    session_name = f"{temp_mngr_ctx.config.prefix}{agent_name}"
    custom_branch = "feature/custom-branch"

    subprocess.run(["git", "init"], cwd=temp_work_dir, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=temp_work_dir,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=temp_work_dir,
        check=True,
        capture_output=True,
    )
    test_file = temp_work_dir / "test.txt"
    test_file.write_text("test content")
    subprocess.run(["git", "add", "."], cwd=temp_work_dir, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "Initial commit"],
        cwd=temp_work_dir,
        check=True,
        capture_output=True,
    )

    branch_result = subprocess.run(
        ["git", "branch", "--show-current"],
        cwd=temp_work_dir,
        capture_output=True,
        text=True,
        check=True,
    )
    current_branch = branch_result.stdout.strip()

    worktree_path: Path | None = None
    with tmux_session_cleanup(session_name):
        try:
            local_provider = get_provider_instance(ProviderInstanceName(LOCAL_PROVIDER_NAME), temp_mngr_ctx)
            local_host = local_provider.get_host(HostName("local"))
            source_location = HostLocation(
                host=local_host,
                path=temp_work_dir,
            )

            agent_options = CreateAgentOptions(
                agent_type=AgentTypeName("worktree-test"),
                name=agent_name,
                command=CommandString("sleep 60"),
                copy_mode=WorkDirCopyMode.WORKTREE,
                git=AgentGitOptions(
                    base_branch=current_branch,
                    is_new_branch=True,
                    new_branch_name=custom_branch,
                ),
            )

            result = create(
                source_location=source_location,
                target_host=local_host,
                agent_options=agent_options,
                mngr_ctx=temp_mngr_ctx,
            )

            assert result.agent.id is not None

            provider = get_provider_instance(LOCAL_PROVIDER_NAME, temp_mngr_ctx)
            host = provider.get_host(result.host.id)
            agents = host.get_agents()
            agent = next((a for a in agents if a.id == result.agent.id), None)
            assert agent is not None

            worktree_path = Path(agent.work_dir)
            result = subprocess.run(
                ["git", "branch", "--show-current"],
                cwd=worktree_path,
                capture_output=True,
                text=True,
                check=True,
            )
            branch_name = result.stdout.strip()
            assert branch_name == custom_branch
        finally:
            if worktree_path is not None:
                subprocess.run(
                    ["git", "worktree", "remove", "--force", str(worktree_path)],
                    cwd=temp_work_dir,
                    capture_output=True,
                )


# =============================================================================
# is_generated_work_dir Tests
# =============================================================================


def test_in_place_mode_sets_is_generated_work_dir_false(
    temp_mngr_ctx: MngrContext,
    temp_work_dir: Path,
    temp_host_dir: Path,
) -> None:
    """Test that in-place mode does not track work_dir as generated."""
    agent_name = AgentName(f"test-in-place-{int(time.time())}")
    session_name = f"{temp_mngr_ctx.config.prefix}{agent_name}"

    with tmux_session_cleanup(session_name):
        local_provider = get_provider_instance(ProviderInstanceName(LOCAL_PROVIDER_NAME), temp_mngr_ctx)
        local_host = local_provider.get_host(HostName("local"))
        source_location = HostLocation(
            host=local_host,
            path=temp_work_dir,
        )

        agent_options = CreateAgentOptions(
            agent_type=AgentTypeName("in-place-test"),
            name=agent_name,
            command=CommandString("sleep 60"),
        )

        result = create(
            source_location=source_location,
            target_host=local_host,
            agent_options=agent_options,
            mngr_ctx=temp_mngr_ctx,
        )

        agents_dir = temp_host_dir / "agents"
        agent_dir = agents_dir / str(result.agent.id)
        data_file = agent_dir / "data.json"
        assert data_file.exists(), "agent data.json should exist"

        data = json.loads(data_file.read_text())
        assert data["work_dir"] == str(temp_work_dir), "work_dir should be the source work_dir"

        host_data_file = temp_host_dir / "data.json"
        host_data = json.loads(host_data_file.read_text()) if host_data_file.exists() else {}
        generated_work_dirs = host_data.get("generated_work_dirs", [])
        assert str(temp_work_dir) not in generated_work_dirs, (
            "work_dir should not be in generated_work_dirs for in-place mode"
        )


def test_worktree_mode_sets_is_generated_work_dir_true(
    temp_mngr_ctx: MngrContext,
    temp_work_dir: Path,
    temp_host_dir: Path,
) -> None:
    """Test that worktree mode tracks work_dir as generated."""
    agent_name = AgentName(f"test-worktree-gen-{int(time.time())}")
    session_name = f"{temp_mngr_ctx.config.prefix}{agent_name}"

    subprocess.run(["git", "init"], cwd=temp_work_dir, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=temp_work_dir,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=temp_work_dir,
        check=True,
        capture_output=True,
    )
    test_file = temp_work_dir / "test.txt"
    test_file.write_text("test content")
    subprocess.run(["git", "add", "."], cwd=temp_work_dir, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "Initial commit"],
        cwd=temp_work_dir,
        check=True,
        capture_output=True,
    )

    worktree_path: Path | None = None
    with tmux_session_cleanup(session_name):
        try:
            local_provider = get_provider_instance(ProviderInstanceName(LOCAL_PROVIDER_NAME), temp_mngr_ctx)
            local_host = local_provider.get_host(HostName("local"))
            source_location = HostLocation(
                host=local_host,
                path=temp_work_dir,
            )

            agent_options = CreateAgentOptions(
                agent_type=AgentTypeName("worktree-gen-test"),
                name=agent_name,
                command=CommandString("sleep 60"),
                copy_mode=WorkDirCopyMode.WORKTREE,
            )

            result = create(
                source_location=source_location,
                target_host=local_host,
                agent_options=agent_options,
                mngr_ctx=temp_mngr_ctx,
            )

            agents_dir = temp_host_dir / "agents"
            agent_dir = agents_dir / str(result.agent.id)
            data_file = agent_dir / "data.json"
            assert data_file.exists(), "agent data.json should exist"

            data = json.loads(data_file.read_text())
            assert data["work_dir"] != str(temp_work_dir), "work_dir should be different from source in worktree mode"

            provider = get_provider_instance(LOCAL_PROVIDER_NAME, temp_mngr_ctx)
            host = provider.get_host(result.host.id)
            agents = host.get_agents()
            agent = next((a for a in agents if a.id == result.agent.id), None)
            assert agent is not None
            worktree_path = Path(agent.work_dir)

            host_data_file = temp_host_dir / "data.json"
            assert host_data_file.exists(), "host data.json should exist"
            host_data = json.loads(host_data_file.read_text())
            generated_work_dirs = host_data.get("generated_work_dirs", [])
            assert str(worktree_path) in generated_work_dirs, (
                "work_dir should be in generated_work_dirs for worktree mode"
            )
        finally:
            if worktree_path is not None:
                subprocess.run(
                    ["git", "worktree", "remove", "--force", str(worktree_path)],
                    cwd=temp_work_dir,
                    capture_output=True,
                )


def test_target_path_different_from_source_sets_is_generated_work_dir_true(
    temp_mngr_ctx: MngrContext,
    temp_work_dir: Path,
    temp_host_dir: Path,
    tmp_path: Path,
) -> None:
    """Test that specifying a different target path tracks work_dir as generated."""
    agent_name = AgentName(f"test-target-diff-{int(time.time())}")
    session_name = f"{temp_mngr_ctx.config.prefix}{agent_name}"
    target_dir = tmp_path / "different_target"

    with tmux_session_cleanup(session_name):
        local_provider = get_provider_instance(ProviderInstanceName(LOCAL_PROVIDER_NAME), temp_mngr_ctx)
        local_host = local_provider.get_host(HostName("local"))
        source_location = HostLocation(
            host=local_host,
            path=temp_work_dir,
        )

        agent_options = CreateAgentOptions(
            agent_type=AgentTypeName("target-diff-test"),
            name=agent_name,
            command=CommandString("sleep 60"),
            target_path=target_dir,
        )

        result = create(
            source_location=source_location,
            target_host=local_host,
            agent_options=agent_options,
            mngr_ctx=temp_mngr_ctx,
        )

        agents_dir = temp_host_dir / "agents"
        agent_dir = agents_dir / str(result.agent.id)
        data_file = agent_dir / "data.json"
        assert data_file.exists(), "agent data.json should exist"

        data = json.loads(data_file.read_text())
        assert data["work_dir"] == str(target_dir), "work_dir should be the target path"

        host_data_file = temp_host_dir / "data.json"
        assert host_data_file.exists(), "host data.json should exist"
        host_data = json.loads(host_data_file.read_text())
        generated_work_dirs = host_data.get("generated_work_dirs", [])
        assert str(target_dir) in generated_work_dirs, (
            "work_dir should be in generated_work_dirs when target differs from source"
        )


def test_target_path_same_as_source_sets_is_generated_work_dir_false(
    temp_mngr_ctx: MngrContext,
    temp_work_dir: Path,
    temp_host_dir: Path,
) -> None:
    """Test that specifying the same target as source path does not track work_dir as generated."""
    agent_name = AgentName(f"test-target-same-{int(time.time())}")
    session_name = f"{temp_mngr_ctx.config.prefix}{agent_name}"

    with tmux_session_cleanup(session_name):
        local_provider = get_provider_instance(ProviderInstanceName(LOCAL_PROVIDER_NAME), temp_mngr_ctx)
        local_host = local_provider.get_host(HostName("local"))
        source_location = HostLocation(
            host=local_host,
            path=temp_work_dir,
        )

        agent_options = CreateAgentOptions(
            agent_type=AgentTypeName("target-same-test"),
            name=agent_name,
            command=CommandString("sleep 60"),
            target_path=temp_work_dir,
        )

        result = create(
            source_location=source_location,
            target_host=local_host,
            agent_options=agent_options,
            mngr_ctx=temp_mngr_ctx,
        )

        agents_dir = temp_host_dir / "agents"
        agent_dir = agents_dir / str(result.agent.id)
        data_file = agent_dir / "data.json"
        assert data_file.exists(), "agent data.json should exist"

        data = json.loads(data_file.read_text())
        assert data["work_dir"] == str(temp_work_dir), "work_dir should be the source/target path"

        host_data_file = temp_host_dir / "data.json"
        host_data = json.loads(host_data_file.read_text()) if host_data_file.exists() else {}
        generated_work_dirs = host_data.get("generated_work_dirs", [])
        assert str(temp_work_dir) not in generated_work_dirs, (
            "work_dir should not be in generated_work_dirs when target equals source"
        )


# =============================================================================
# on_before_create Hook Tests
# =============================================================================


class PluginModifyingAgentOptions:
    """Test plugin that modifies agent_options."""

    @hookimpl
    def on_before_create(self, args: OnBeforeCreateArgs) -> OnBeforeCreateArgs | None:
        # Modify the agent name by adding a prefix
        new_options = args.agent_options.model_copy(update={"name": AgentName(f"modified-{args.agent_options.name}")})
        return args.model_copy(update={"agent_options": new_options})


class PluginModifyingCreateWorkDir:
    """Test plugin that modifies create_work_dir."""

    @hookimpl
    def on_before_create(self, args: OnBeforeCreateArgs) -> OnBeforeCreateArgs | None:
        # Force create_work_dir to False
        return args.model_copy(update={"create_work_dir": False})


class PluginReturningNone:
    """Test plugin that returns None (passes through unchanged)."""

    @hookimpl
    def on_before_create(self, args: OnBeforeCreateArgs) -> OnBeforeCreateArgs | None:
        return None


class PluginChainA:
    """First plugin in a chain test - adds 'A' to agent name."""

    @hookimpl
    def on_before_create(self, args: OnBeforeCreateArgs) -> OnBeforeCreateArgs | None:
        new_name = AgentName(f"{args.agent_options.name}-A")
        new_options = args.agent_options.model_copy(update={"name": new_name})
        return args.model_copy(update={"agent_options": new_options})


class PluginChainB:
    """Second plugin in a chain test - adds 'B' to agent name."""

    @hookimpl
    def on_before_create(self, args: OnBeforeCreateArgs) -> OnBeforeCreateArgs | None:
        new_name = AgentName(f"{args.agent_options.name}-B")
        new_options = args.agent_options.model_copy(update={"name": new_name})
        return args.model_copy(update={"agent_options": new_options})


def test_on_before_create_hook_modifies_agent_options(
    temp_mngr_ctx: MngrContext,
    temp_work_dir: Path,
) -> None:
    """Test that on_before_create hook can modify agent_options."""
    # Create a new plugin manager with our test plugin
    pm = pluggy.PluginManager("mngr")
    pm.add_hookspecs(hookspecs)
    pm.register(PluginModifyingAgentOptions())

    # Create a modified context with our test plugin manager
    test_ctx = temp_mngr_ctx.model_copy(update={"pm": pm})

    local_provider = get_provider_instance(ProviderInstanceName(LOCAL_PROVIDER_NAME), test_ctx)
    local_host = local_provider.get_host(HostName("local"))

    agent_options = CreateAgentOptions(
        agent_type=AgentTypeName("test"),
        name=AgentName("original-name"),
        command=CommandString("sleep 1"),
    )

    # Call the hook helper directly to verify modification
    target_host, modified_options, create_work_dir = _call_on_before_create_hooks(
        test_ctx, local_host, agent_options, True
    )

    # The plugin should have modified the name
    assert modified_options.name == AgentName("modified-original-name")
    assert create_work_dir is True


def test_on_before_create_hook_modifies_create_work_dir(
    temp_mngr_ctx: MngrContext,
    temp_work_dir: Path,
) -> None:
    """Test that on_before_create hook can modify create_work_dir."""
    pm = pluggy.PluginManager("mngr")
    pm.add_hookspecs(hookspecs)
    pm.register(PluginModifyingCreateWorkDir())

    test_ctx = temp_mngr_ctx.model_copy(update={"pm": pm})

    local_provider = get_provider_instance(ProviderInstanceName(LOCAL_PROVIDER_NAME), test_ctx)
    local_host = local_provider.get_host(HostName("local"))

    agent_options = CreateAgentOptions(
        agent_type=AgentTypeName("test"),
        name=AgentName("test-agent"),
        command=CommandString("sleep 1"),
    )

    # Call with create_work_dir=True, plugin should change it to False
    target_host, modified_options, create_work_dir = _call_on_before_create_hooks(
        test_ctx, local_host, agent_options, True
    )

    assert create_work_dir is False


def test_on_before_create_hook_returning_none_passes_through(
    temp_mngr_ctx: MngrContext,
    temp_work_dir: Path,
) -> None:
    """Test that on_before_create returning None passes values unchanged."""
    pm = pluggy.PluginManager("mngr")
    pm.add_hookspecs(hookspecs)
    pm.register(PluginReturningNone())

    test_ctx = temp_mngr_ctx.model_copy(update={"pm": pm})

    local_provider = get_provider_instance(ProviderInstanceName(LOCAL_PROVIDER_NAME), test_ctx)
    local_host = local_provider.get_host(HostName("local"))

    original_name = AgentName("unchanged-name")
    agent_options = CreateAgentOptions(
        agent_type=AgentTypeName("test"),
        name=original_name,
        command=CommandString("sleep 1"),
    )

    target_host, modified_options, create_work_dir = _call_on_before_create_hooks(
        test_ctx, local_host, agent_options, True
    )

    # Values should be unchanged
    assert modified_options.name == original_name
    assert create_work_dir is True


def test_on_before_create_hooks_chain_in_order(
    temp_mngr_ctx: MngrContext,
    temp_work_dir: Path,
) -> None:
    """Test that multiple on_before_create hooks chain properly."""
    pm = pluggy.PluginManager("mngr")
    pm.add_hookspecs(hookspecs)
    # Register plugins in order A, B
    pm.register(PluginChainA())
    pm.register(PluginChainB())

    test_ctx = temp_mngr_ctx.model_copy(update={"pm": pm})

    local_provider = get_provider_instance(ProviderInstanceName(LOCAL_PROVIDER_NAME), test_ctx)
    local_host = local_provider.get_host(HostName("local"))

    agent_options = CreateAgentOptions(
        agent_type=AgentTypeName("test"),
        name=AgentName("base"),
        command=CommandString("sleep 1"),
    )

    target_host, modified_options, create_work_dir = _call_on_before_create_hooks(
        test_ctx, local_host, agent_options, True
    )

    # Both plugins should have modified the name in order
    # A adds "-A", then B adds "-B" to that result
    assert modified_options.name == AgentName("base-A-B")


# =============================================================================
# Provisioning Hook Tests
# =============================================================================


class ProvisioningHookTracker:
    """Test plugin that tracks which provisioning hooks were called and in what order."""

    def __init__(self) -> None:
        self.calls: list[str] = []
        self.agents_seen: list[str] = []

    @hookimpl
    def on_before_agent_provisioning(
        self,
        agent: AgentInterface,
        host: HostInterface,
        options: CreateAgentOptions,
        mngr_ctx: MngrContext,
    ) -> None:
        self.calls.append("on_before_agent_provisioning")
        self.agents_seen.append(str(agent.name))

    @hookimpl
    def get_provision_file_transfers(
        self,
        agent: AgentInterface,
        host: HostInterface,
        options: CreateAgentOptions,
        mngr_ctx: MngrContext,
    ) -> list[FileTransferSpec] | None:
        self.calls.append("get_provision_file_transfers")
        return None

    @hookimpl
    def provision_agent(
        self,
        agent: AgentInterface,
        host: HostInterface,
        options: CreateAgentOptions,
        mngr_ctx: MngrContext,
    ) -> None:
        self.calls.append("provision_agent")

    @hookimpl
    def on_after_agent_provisioning(
        self,
        agent: AgentInterface,
        host: HostInterface,
        options: CreateAgentOptions,
        mngr_ctx: MngrContext,
    ) -> None:
        self.calls.append("on_after_agent_provisioning")


def test_provisioning_hooks_called_in_correct_order(
    temp_mngr_ctx: MngrContext,
    temp_work_dir: Path,
) -> None:
    """Test that provisioning hooks are called in the correct order."""
    agent_name = AgentName(f"test-prov-order-{int(time.time())}")
    session_name = f"{temp_mngr_ctx.config.prefix}{agent_name}"

    tracker = ProvisioningHookTracker()

    pm = pluggy.PluginManager("mngr")
    pm.add_hookspecs(hookspecs)
    pm.register(tracker)

    test_ctx = temp_mngr_ctx.model_copy(update={"pm": pm})

    with tmux_session_cleanup(session_name):
        local_provider = get_provider_instance(ProviderInstanceName(LOCAL_PROVIDER_NAME), test_ctx)
        local_host = local_provider.get_host(HostName("local"))
        source_location = HostLocation(
            host=local_host,
            path=temp_work_dir,
        )

        agent_options = CreateAgentOptions(
            agent_type=AgentTypeName("test"),
            name=agent_name,
            command=CommandString("sleep 60"),
        )

        create(
            source_location=source_location,
            target_host=local_host,
            agent_options=agent_options,
            mngr_ctx=test_ctx,
        )

    # Verify hooks were called in the correct order
    expected_order = [
        "on_before_agent_provisioning",
        "get_provision_file_transfers",
        "provision_agent",
        "on_after_agent_provisioning",
    ]
    assert tracker.calls == expected_order, f"Expected {expected_order}, got {tracker.calls}"


class FileTransferPlugin:
    """Test plugin that returns file transfer specs."""

    def __init__(self, transfers: list[FileTransferSpec]) -> None:
        self.transfers = transfers
        self.transfer_called = False

    @hookimpl
    def get_provision_file_transfers(
        self,
        agent: AgentInterface,
        host: HostInterface,
        options: CreateAgentOptions,
        mngr_ctx: MngrContext,
    ) -> list[FileTransferSpec] | None:
        self.transfer_called = True
        return self.transfers


def test_file_transfer_plugin_copies_files(
    temp_mngr_ctx: MngrContext,
    temp_work_dir: Path,
    tmp_path: Path,
) -> None:
    """Test that get_provision_file_transfers hook copies files to the agent."""
    agent_name = AgentName(f"test-file-transfer-{int(time.time())}")
    session_name = f"{temp_mngr_ctx.config.prefix}{agent_name}"

    # Create a local file to transfer
    local_file = tmp_path / "test_config.txt"
    local_file.write_text("test configuration content")

    # Set up plugin that transfers the file
    plugin = FileTransferPlugin(
        [
            FileTransferSpec(
                local_path=local_file,
                agent_path=RelativePath("transferred_config.txt"),
                is_required=True,
            )
        ]
    )

    pm = pluggy.PluginManager("mngr")
    pm.add_hookspecs(hookspecs)
    pm.register(plugin)

    test_ctx = temp_mngr_ctx.model_copy(update={"pm": pm})

    with tmux_session_cleanup(session_name):
        local_provider = get_provider_instance(ProviderInstanceName(LOCAL_PROVIDER_NAME), test_ctx)
        local_host = local_provider.get_host(HostName("local"))
        source_location = HostLocation(
            host=local_host,
            path=temp_work_dir,
        )

        agent_options = CreateAgentOptions(
            agent_type=AgentTypeName("test"),
            name=agent_name,
            command=CommandString("sleep 60"),
        )

        result = create(
            source_location=source_location,
            target_host=local_host,
            agent_options=agent_options,
            mngr_ctx=test_ctx,
        )

        # Verify the file was transferred
        assert plugin.transfer_called
        transferred_file = result.agent.work_dir / "transferred_config.txt"
        assert transferred_file.exists(), f"Expected {transferred_file} to exist"
        assert transferred_file.read_text() == "test configuration content"


def test_file_transfer_missing_required_file_raises_error(
    temp_mngr_ctx: MngrContext,
    temp_work_dir: Path,
    tmp_path: Path,
) -> None:
    """Test that missing required files raise an error."""
    agent_name = AgentName(f"test-missing-file-{int(time.time())}")
    session_name = f"{temp_mngr_ctx.config.prefix}{agent_name}"

    # Set up plugin that tries to transfer a non-existent file
    nonexistent_file = tmp_path / "does_not_exist.txt"
    plugin = FileTransferPlugin(
        [
            FileTransferSpec(
                local_path=nonexistent_file,
                agent_path=RelativePath("config.txt"),
                is_required=True,
            )
        ]
    )

    pm = pluggy.PluginManager("mngr")
    pm.add_hookspecs(hookspecs)
    pm.register(plugin)

    test_ctx = temp_mngr_ctx.model_copy(update={"pm": pm})

    with tmux_session_cleanup(session_name):
        local_provider = get_provider_instance(ProviderInstanceName(LOCAL_PROVIDER_NAME), test_ctx)
        local_host = local_provider.get_host(HostName("local"))
        source_location = HostLocation(
            host=local_host,
            path=temp_work_dir,
        )

        agent_options = CreateAgentOptions(
            agent_type=AgentTypeName("test"),
            name=agent_name,
            command=CommandString("sleep 60"),
        )

        with pytest.raises(MngrError) as exc_info:
            create(
                source_location=source_location,
                target_host=local_host,
                agent_options=agent_options,
                mngr_ctx=test_ctx,
            )

        assert "not found" in str(exc_info.value).lower()


def test_file_transfer_optional_file_skipped_when_missing(
    temp_mngr_ctx: MngrContext,
    temp_work_dir: Path,
    tmp_path: Path,
) -> None:
    """Test that optional files are skipped when missing."""
    agent_name = AgentName(f"test-optional-file-{int(time.time())}")
    session_name = f"{temp_mngr_ctx.config.prefix}{agent_name}"

    # Set up plugin that tries to transfer a non-existent optional file
    nonexistent_file = tmp_path / "optional_config.txt"
    plugin = FileTransferPlugin(
        [
            FileTransferSpec(
                local_path=nonexistent_file,
                agent_path=RelativePath("config.txt"),
                is_required=False,
            )
        ]
    )

    pm = pluggy.PluginManager("mngr")
    pm.add_hookspecs(hookspecs)
    pm.register(plugin)

    test_ctx = temp_mngr_ctx.model_copy(update={"pm": pm})

    with tmux_session_cleanup(session_name):
        local_provider = get_provider_instance(ProviderInstanceName(LOCAL_PROVIDER_NAME), test_ctx)
        local_host = local_provider.get_host(HostName("local"))
        source_location = HostLocation(
            host=local_host,
            path=temp_work_dir,
        )

        agent_options = CreateAgentOptions(
            agent_type=AgentTypeName("test"),
            name=agent_name,
            command=CommandString("sleep 60"),
        )

        # Should not raise
        result = create(
            source_location=source_location,
            target_host=local_host,
            agent_options=agent_options,
            mngr_ctx=test_ctx,
        )

        assert plugin.transfer_called
        # The optional file should not exist
        optional_file = result.agent.work_dir / "config.txt"
        assert not optional_file.exists()


class ValidationPlugin:
    """Test plugin that validates preconditions."""

    def __init__(self, should_fail: bool = False) -> None:
        self.should_fail = should_fail
        self.validation_called = False

    @hookimpl
    def on_before_agent_provisioning(
        self,
        agent: AgentInterface,
        host: HostInterface,
        options: CreateAgentOptions,
        mngr_ctx: MngrContext,
    ) -> None:
        self.validation_called = True
        if self.should_fail:
            raise MngrError("Validation failed: missing required environment variable")


def test_validation_hook_can_fail_provisioning(
    temp_mngr_ctx: MngrContext,
    temp_work_dir: Path,
) -> None:
    """Test that on_before_agent_provisioning can fail provisioning."""
    agent_name = AgentName(f"test-validation-fail-{int(time.time())}")
    session_name = f"{temp_mngr_ctx.config.prefix}{agent_name}"

    plugin = ValidationPlugin(should_fail=True)

    pm = pluggy.PluginManager("mngr")
    pm.add_hookspecs(hookspecs)
    pm.register(plugin)

    test_ctx = temp_mngr_ctx.model_copy(update={"pm": pm})

    with tmux_session_cleanup(session_name):
        local_provider = get_provider_instance(ProviderInstanceName(LOCAL_PROVIDER_NAME), test_ctx)
        local_host = local_provider.get_host(HostName("local"))
        source_location = HostLocation(
            host=local_host,
            path=temp_work_dir,
        )

        agent_options = CreateAgentOptions(
            agent_type=AgentTypeName("test"),
            name=agent_name,
            command=CommandString("sleep 60"),
        )

        with pytest.raises(MngrError) as exc_info:
            create(
                source_location=source_location,
                target_host=local_host,
                agent_options=agent_options,
                mngr_ctx=test_ctx,
            )

        assert "Validation failed" in str(exc_info.value)
        assert plugin.validation_called
