from collections.abc import Sequence
from datetime import datetime
from datetime import timezone
from typing import Final

import pluggy
import pytest
from click.testing import CliRunner

import imbue.mngr.cli.snapshot as snapshot_module
from imbue.mngr.cli.snapshot import SnapshotCreateCliOptions
from imbue.mngr.cli.snapshot import SnapshotDestroyCliOptions
from imbue.mngr.cli.snapshot import SnapshotListCliOptions
from imbue.mngr.cli.snapshot import snapshot
from imbue.mngr.interfaces.data_types import SnapshotInfo
from imbue.mngr.primitives import HostId
from imbue.mngr.primitives import ProviderInstanceName
from imbue.mngr.primitives import SnapshotId
from imbue.mngr.primitives import SnapshotName

# Valid HostId for use in test data (host- prefix + 32 hex characters)
VALID_HOST_ID: Final[str] = "host-" + "a" * 32


# =============================================================================
# Fake provider for testing snapshot operations
# =============================================================================


class _FakeSnapshotProvider:
    """Minimal fake provider for testing snapshot CLI commands.

    Tracks calls to create_snapshot, list_snapshots, and delete_snapshot
    so tests can verify the correct operations were performed without
    using unittest.mock.
    """

    def __init__(
        self,
        *,
        is_snapshot_supported: bool = True,
        create_return: SnapshotId | None = None,
        list_return: Sequence[SnapshotInfo] = (),
    ) -> None:
        self.supports_snapshots = is_snapshot_supported
        self._create_return = create_return if create_return is not None else SnapshotId("snap-fake")
        self._list_return = list(list_return)
        self.create_snapshot_calls: list[tuple[HostId, SnapshotName | None]] = []
        self.delete_snapshot_calls: list[tuple[HostId, SnapshotId]] = []

    def create_snapshot(
        self,
        host_id: HostId,
        name: SnapshotName | None = None,
    ) -> SnapshotId:
        self.create_snapshot_calls.append((host_id, name))
        return self._create_return

    def list_snapshots(self, host_id: HostId) -> list[SnapshotInfo]:
        return self._list_return

    def delete_snapshot(self, host_id: HostId, snapshot_id: SnapshotId) -> None:
        self.delete_snapshot_calls.append((host_id, snapshot_id))


def _make_resolve_return(
    host_id: str = VALID_HOST_ID,
    provider_name: str = "modal",
    agent_names: list[str] | None = None,
) -> list[tuple[str, ProviderInstanceName, list[str]]]:
    return [(host_id, ProviderInstanceName(provider_name), agent_names or ["my-agent"])]


# =============================================================================
# Options classes tests
# =============================================================================


def test_snapshot_create_cli_options_fields() -> None:
    """Test SnapshotCreateCliOptions has required fields."""
    opts = SnapshotCreateCliOptions(
        agents=("agent1",),
        agent_list=("agent2",),
        hosts=("host1",),
        all_agents=False,
        name="my-snapshot",
        dry_run=True,
        include=(),
        exclude=(),
        stdin=False,
        tag=(),
        description=None,
        restart_if_larger_than=None,
        pause_during=True,
        wait=True,
        output_format="human",
        quiet=False,
        verbose=0,
        log_file=None,
        log_commands=None,
        log_command_output=None,
        log_env_vars=None,
        project_context_path=None,
        plugin=(),
        disable_plugin=(),
    )
    assert opts.agents == ("agent1",)
    assert opts.agent_list == ("agent2",)
    assert opts.hosts == ("host1",)
    assert opts.all_agents is False
    assert opts.name == "my-snapshot"
    assert opts.dry_run is True


def test_snapshot_list_cli_options_fields() -> None:
    """Test SnapshotListCliOptions has required fields."""
    opts = SnapshotListCliOptions(
        agents=("agent1",),
        agent_list=(),
        all_agents=False,
        limit=10,
        include=(),
        exclude=(),
        after=None,
        before=None,
        output_format="json",
        quiet=False,
        verbose=0,
        log_file=None,
        log_commands=None,
        log_command_output=None,
        log_env_vars=None,
        project_context_path=None,
        plugin=(),
        disable_plugin=(),
    )
    assert opts.agents == ("agent1",)
    assert opts.limit == 10


def test_snapshot_destroy_cli_options_fields() -> None:
    """Test SnapshotDestroyCliOptions has required fields."""
    opts = SnapshotDestroyCliOptions(
        agents=("agent1",),
        agent_list=(),
        snapshots=("snap-123",),
        all_snapshots=False,
        force=True,
        dry_run=False,
        include=(),
        exclude=(),
        stdin=False,
        output_format="human",
        quiet=False,
        verbose=0,
        log_file=None,
        log_commands=None,
        log_command_output=None,
        log_env_vars=None,
        project_context_path=None,
        plugin=(),
        disable_plugin=(),
    )
    assert opts.snapshots == ("snap-123",)
    assert opts.force is True


# =============================================================================
# create subcommand tests
# =============================================================================


def test_snapshot_create_success(
    monkeypatch: pytest.MonkeyPatch,
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test successful snapshot creation."""
    fake_provider = _FakeSnapshotProvider(create_return=SnapshotId("snap-abc"))
    monkeypatch.setattr(snapshot_module, "_resolve_snapshot_hosts", lambda **_kwargs: _make_resolve_return())
    monkeypatch.setattr(snapshot_module, "get_provider_instance", lambda _name, _ctx: fake_provider)

    result = cli_runner.invoke(
        snapshot,
        ["create", "my-agent"],
        obj=plugin_manager,
        catch_exceptions=False,
    )
    assert result.exit_code == 0
    assert len(fake_provider.create_snapshot_calls) == 1


def test_snapshot_create_json_output(
    monkeypatch: pytest.MonkeyPatch,
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test snapshot create with JSON output format."""
    fake_provider = _FakeSnapshotProvider(create_return=SnapshotId("snap-json"))
    monkeypatch.setattr(snapshot_module, "_resolve_snapshot_hosts", lambda **_kwargs: _make_resolve_return())
    monkeypatch.setattr(snapshot_module, "get_provider_instance", lambda _name, _ctx: fake_provider)

    result = cli_runner.invoke(
        snapshot,
        ["create", "my-agent", "--format", "json"],
        obj=plugin_manager,
        catch_exceptions=False,
    )
    assert result.exit_code == 0
    assert "snap-json" in result.output
    assert "snapshots_created" in result.output


# =============================================================================
# list subcommand tests
# =============================================================================


def test_snapshot_list_success(
    monkeypatch: pytest.MonkeyPatch,
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test successful snapshot listing with JSON output."""
    fake_provider = _FakeSnapshotProvider(
        list_return=[
            SnapshotInfo(
                id=SnapshotId("snap-001"),
                name=SnapshotName("before-refactor"),
                created_at=datetime(2024, 1, 15, 14, 30, 0, tzinfo=timezone.utc),
                size_bytes=256 * 1024 * 1024,
            ),
            SnapshotInfo(
                id=SnapshotId("snap-002"),
                name=SnapshotName("auto-stop"),
                created_at=datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc),
                size_bytes=64 * 1024 * 1024,
            ),
        ],
    )
    monkeypatch.setattr(snapshot_module, "_resolve_snapshot_hosts", lambda **_kwargs: _make_resolve_return())
    monkeypatch.setattr(snapshot_module, "get_provider_instance", lambda _name, _ctx: fake_provider)

    result = cli_runner.invoke(
        snapshot,
        ["list", "my-agent", "--format", "json"],
        obj=plugin_manager,
        catch_exceptions=False,
    )
    assert result.exit_code == 0
    assert "snap-001" in result.output
    assert "before-refactor" in result.output
    assert "snap-002" in result.output
    assert "auto-stop" in result.output


def test_snapshot_list_with_limit(
    monkeypatch: pytest.MonkeyPatch,
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test snapshot list with --limit."""
    fake_provider = _FakeSnapshotProvider(
        list_return=[
            SnapshotInfo(
                id=SnapshotId("snap-001"),
                name=SnapshotName("first"),
                created_at=datetime(2024, 1, 15, 14, 30, 0, tzinfo=timezone.utc),
            ),
            SnapshotInfo(
                id=SnapshotId("snap-002"),
                name=SnapshotName("second"),
                created_at=datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc),
            ),
        ],
    )
    monkeypatch.setattr(snapshot_module, "_resolve_snapshot_hosts", lambda **_kwargs: _make_resolve_return())
    monkeypatch.setattr(snapshot_module, "get_provider_instance", lambda _name, _ctx: fake_provider)

    result = cli_runner.invoke(
        snapshot,
        ["list", "my-agent", "--limit", "1", "--format", "json"],
        obj=plugin_manager,
        catch_exceptions=False,
    )
    assert result.exit_code == 0
    assert "snap-001" in result.output
    assert "snap-002" not in result.output


def test_snapshot_list_json_output(
    monkeypatch: pytest.MonkeyPatch,
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test snapshot list with JSON output."""
    fake_provider = _FakeSnapshotProvider(
        list_return=[
            SnapshotInfo(
                id=SnapshotId("snap-json-1"),
                name=SnapshotName("test"),
                created_at=datetime(2024, 1, 15, 14, 30, 0, tzinfo=timezone.utc),
                size_bytes=1024,
            ),
        ],
    )
    monkeypatch.setattr(snapshot_module, "_resolve_snapshot_hosts", lambda **_kwargs: _make_resolve_return())
    monkeypatch.setattr(snapshot_module, "get_provider_instance", lambda _name, _ctx: fake_provider)

    result = cli_runner.invoke(
        snapshot,
        ["list", "my-agent", "--format", "json"],
        obj=plugin_manager,
        catch_exceptions=False,
    )
    assert result.exit_code == 0
    assert "snap-json-1" in result.output
    assert "snapshots" in result.output


def test_snapshot_list_jsonl_output(
    monkeypatch: pytest.MonkeyPatch,
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test snapshot list with JSONL output."""
    fake_provider = _FakeSnapshotProvider(
        list_return=[
            SnapshotInfo(
                id=SnapshotId("snap-jsonl-1"),
                name=SnapshotName("test"),
                created_at=datetime(2024, 1, 15, 14, 30, 0, tzinfo=timezone.utc),
            ),
        ],
    )
    monkeypatch.setattr(snapshot_module, "_resolve_snapshot_hosts", lambda **_kwargs: _make_resolve_return())
    monkeypatch.setattr(snapshot_module, "get_provider_instance", lambda _name, _ctx: fake_provider)

    result = cli_runner.invoke(
        snapshot,
        ["list", "my-agent", "--format", "jsonl"],
        obj=plugin_manager,
        catch_exceptions=False,
    )
    assert result.exit_code == 0
    assert "snap-jsonl-1" in result.output


def test_snapshot_list_no_snapshots(
    monkeypatch: pytest.MonkeyPatch,
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test listing when there are no snapshots (JSON output)."""
    fake_provider = _FakeSnapshotProvider(list_return=[])
    monkeypatch.setattr(snapshot_module, "_resolve_snapshot_hosts", lambda **_kwargs: _make_resolve_return())
    monkeypatch.setattr(snapshot_module, "get_provider_instance", lambda _name, _ctx: fake_provider)

    result = cli_runner.invoke(
        snapshot,
        ["list", "my-agent", "--format", "json"],
        obj=plugin_manager,
        catch_exceptions=False,
    )
    assert result.exit_code == 0
    assert '"count": 0' in result.output


# =============================================================================
# destroy subcommand tests
# =============================================================================


def test_snapshot_destroy_with_force(
    monkeypatch: pytest.MonkeyPatch,
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test destroying a specific snapshot with --force."""
    fake_provider = _FakeSnapshotProvider()
    monkeypatch.setattr(snapshot_module, "_resolve_snapshot_hosts", lambda **_kwargs: _make_resolve_return())
    monkeypatch.setattr(snapshot_module, "get_provider_instance", lambda _name, _ctx: fake_provider)

    result = cli_runner.invoke(
        snapshot,
        ["destroy", "my-agent", "--snapshot", "snap-123", "--force"],
        obj=plugin_manager,
        catch_exceptions=False,
    )
    assert result.exit_code == 0
    assert len(fake_provider.delete_snapshot_calls) == 1


def test_snapshot_destroy_all_snapshots_with_force(
    monkeypatch: pytest.MonkeyPatch,
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test destroying all snapshots with --force."""
    fake_provider = _FakeSnapshotProvider(
        list_return=[
            SnapshotInfo(
                id=SnapshotId("snap-001"),
                name=SnapshotName("first"),
                created_at=datetime(2024, 1, 15, 14, 30, 0, tzinfo=timezone.utc),
            ),
            SnapshotInfo(
                id=SnapshotId("snap-002"),
                name=SnapshotName("second"),
                created_at=datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc),
            ),
        ],
    )
    monkeypatch.setattr(snapshot_module, "_resolve_snapshot_hosts", lambda **_kwargs: _make_resolve_return())
    monkeypatch.setattr(snapshot_module, "get_provider_instance", lambda _name, _ctx: fake_provider)

    result = cli_runner.invoke(
        snapshot,
        ["destroy", "my-agent", "--all-snapshots", "--force"],
        obj=plugin_manager,
        catch_exceptions=False,
    )
    assert result.exit_code == 0
    assert len(fake_provider.delete_snapshot_calls) == 2


def test_snapshot_destroy_dry_run(
    monkeypatch: pytest.MonkeyPatch,
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test destroy --dry-run does not actually delete (JSONL output for stdout)."""
    fake_provider = _FakeSnapshotProvider(
        list_return=[
            SnapshotInfo(
                id=SnapshotId("snap-001"),
                name=SnapshotName("first"),
                created_at=datetime(2024, 1, 15, 14, 30, 0, tzinfo=timezone.utc),
            ),
        ],
    )
    monkeypatch.setattr(snapshot_module, "_resolve_snapshot_hosts", lambda **_kwargs: _make_resolve_return())
    monkeypatch.setattr(snapshot_module, "get_provider_instance", lambda _name, _ctx: fake_provider)

    result = cli_runner.invoke(
        snapshot,
        ["destroy", "my-agent", "--all-snapshots", "--dry-run", "--format", "jsonl"],
        obj=plugin_manager,
        catch_exceptions=False,
    )
    assert result.exit_code == 0
    assert "Would destroy" in result.output
    assert len(fake_provider.delete_snapshot_calls) == 0


def test_snapshot_destroy_json_output(
    monkeypatch: pytest.MonkeyPatch,
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test destroy with JSON output."""
    fake_provider = _FakeSnapshotProvider()
    monkeypatch.setattr(snapshot_module, "_resolve_snapshot_hosts", lambda **_kwargs: _make_resolve_return())
    monkeypatch.setattr(snapshot_module, "get_provider_instance", lambda _name, _ctx: fake_provider)

    result = cli_runner.invoke(
        snapshot,
        ["destroy", "my-agent", "--snapshot", "snap-123", "--force", "--format", "json"],
        obj=plugin_manager,
        catch_exceptions=False,
    )
    assert result.exit_code == 0
    assert "snapshots_destroyed" in result.output


def test_snapshot_destroy_no_snapshots_found(
    monkeypatch: pytest.MonkeyPatch,
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test destroy --all-snapshots when no snapshots exist (JSON output)."""
    fake_provider = _FakeSnapshotProvider(list_return=[])
    monkeypatch.setattr(snapshot_module, "_resolve_snapshot_hosts", lambda **_kwargs: _make_resolve_return())
    monkeypatch.setattr(snapshot_module, "get_provider_instance", lambda _name, _ctx: fake_provider)

    result = cli_runner.invoke(
        snapshot,
        ["destroy", "my-agent", "--all-snapshots", "--force", "--format", "json"],
        obj=plugin_manager,
        catch_exceptions=False,
    )
    assert result.exit_code == 0
    assert '"count": 0' in result.output


# =============================================================================
# Future option tests
# =============================================================================


def test_snapshot_create_include_raises_not_implemented(
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test that --include raises NotImplementedError."""
    result = cli_runner.invoke(
        snapshot,
        ["create", "my-agent", "--include", "some-filter"],
        obj=plugin_manager,
        catch_exceptions=True,
    )
    assert result.exit_code != 0


def test_snapshot_create_exclude_raises_not_implemented(
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test that --exclude raises NotImplementedError."""
    result = cli_runner.invoke(
        snapshot,
        ["create", "my-agent", "--exclude", "some-filter"],
        obj=plugin_manager,
        catch_exceptions=True,
    )
    assert result.exit_code != 0


def test_snapshot_create_stdin_raises_not_implemented(
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test that --stdin raises NotImplementedError."""
    result = cli_runner.invoke(
        snapshot,
        ["create", "my-agent", "--stdin"],
        obj=plugin_manager,
        catch_exceptions=True,
    )
    assert result.exit_code != 0


def test_snapshot_create_tag_raises_not_implemented(
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test that --tag raises NotImplementedError."""
    result = cli_runner.invoke(
        snapshot,
        ["create", "my-agent", "--tag", "key=value"],
        obj=plugin_manager,
        catch_exceptions=True,
    )
    assert result.exit_code != 0


def test_snapshot_create_description_raises_not_implemented(
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test that --description raises NotImplementedError."""
    result = cli_runner.invoke(
        snapshot,
        ["create", "my-agent", "--description", "some desc"],
        obj=plugin_manager,
        catch_exceptions=True,
    )
    assert result.exit_code != 0


def test_snapshot_create_no_wait_raises_not_implemented(
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test that --no-wait raises NotImplementedError."""
    result = cli_runner.invoke(
        snapshot,
        ["create", "my-agent", "--no-wait"],
        obj=plugin_manager,
        catch_exceptions=True,
    )
    assert result.exit_code != 0


def test_snapshot_list_after_raises_not_implemented(
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test that --after raises NotImplementedError."""
    result = cli_runner.invoke(
        snapshot,
        ["list", "my-agent", "--after", "2024-01-01"],
        obj=plugin_manager,
        catch_exceptions=True,
    )
    assert result.exit_code != 0


def test_snapshot_destroy_stdin_raises_not_implemented(
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test that --stdin on destroy raises NotImplementedError."""
    result = cli_runner.invoke(
        snapshot,
        ["destroy", "my-agent", "--all-snapshots", "--stdin"],
        obj=plugin_manager,
        catch_exceptions=True,
    )
    assert result.exit_code != 0
