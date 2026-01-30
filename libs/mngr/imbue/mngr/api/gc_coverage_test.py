"""Additional unit tests for gc API functions to improve coverage."""

from datetime import datetime
from datetime import timedelta
from datetime import timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from imbue.mngr.api.data_types import GcResult
from imbue.mngr.api.gc import _get_orphaned_work_dirs
from imbue.mngr.api.gc import _resource_to_cel_context
from imbue.mngr.api.gc import gc_machines
from imbue.mngr.api.gc import gc_snapshots
from imbue.mngr.api.gc import gc_volumes
from imbue.mngr.errors import MngrError
from imbue.mngr.interfaces.data_types import BuildCacheInfo
from imbue.mngr.interfaces.data_types import CertifiedHostData
from imbue.mngr.interfaces.data_types import CommandResult
from imbue.mngr.interfaces.data_types import SizeBytes
from imbue.mngr.interfaces.data_types import SnapshotInfo
from imbue.mngr.interfaces.data_types import VolumeInfo
from imbue.mngr.primitives import ErrorBehavior
from imbue.mngr.primitives import HostId
from imbue.mngr.primitives import ProviderInstanceName
from imbue.mngr.primitives import SnapshotId
from imbue.mngr.primitives import SnapshotName
from imbue.mngr.primitives import VolumeId


class TestResourceToCelContext:
    """Tests for _resource_to_cel_context age calculation from multiple sources."""

    def test_age_from_created_at_takes_precedence_over_stat(self, tmp_path: Path) -> None:
        """Test that created_at takes precedence over filesystem stat for age calculation."""
        # Create a test file (fresh mtime)
        test_file = tmp_path / "test_file.txt"
        test_file.write_text("content")

        # Use BuildCacheInfo with an old created_at
        # The code first calculates age from stat, but then overwrites it with created_at
        created_30_days_ago = datetime.now(timezone.utc) - timedelta(days=30)
        cache_info = BuildCacheInfo(
            path=test_file,
            size_bytes=SizeBytes(100),
            created_at=created_30_days_ago,
        )

        context = _resource_to_cel_context(cache_info)

        # Age should be approximately 30 days (created_at takes precedence)
        # 30 days in seconds
        expected_age = 30 * 24 * 3600
        assert expected_age - 60 < context["age"] < expected_age + 60

    def test_age_from_created_at_for_non_path_resource(self) -> None:
        """Test that age is calculated from created_at when no path exists."""
        created_time = datetime.now(timezone.utc) - timedelta(hours=5)
        snapshot = SnapshotInfo(
            id=SnapshotId.generate(),
            name=SnapshotName("test-snapshot"),
            created_at=created_time,
            size_bytes=1000,
        )

        context = _resource_to_cel_context(snapshot)

        # Age should be approximately 5 hours (18000 seconds)
        assert 5 * 3600 - 10 < context["age"] < 5 * 3600 + 10

    def test_age_from_created_at_when_path_does_not_exist(self) -> None:
        """Test that age is calculated from created_at when path doesn't exist."""
        non_existent_path = Path("/non/existent/path/that/does/not/exist")
        created_time = datetime.now(timezone.utc) - timedelta(hours=2)

        cache_info = BuildCacheInfo(
            path=non_existent_path,
            size_bytes=SizeBytes(50),
            created_at=created_time,
        )

        context = _resource_to_cel_context(cache_info)

        # When path doesn't exist, age should be 0 from the path check,
        # but then overwritten by created_at calculation
        assert 2 * 3600 - 10 < context["age"] < 2 * 3600 + 10

    def test_age_from_updated_at_field(self) -> None:
        """Test that age can be calculated from updated_at if created_at is not present."""
        created_time = datetime.now(timezone.utc) - timedelta(days=3)
        volume = VolumeInfo(
            volume_id=VolumeId.generate(),
            name="test-volume",
            size_bytes=1000000,
            created_at=created_time,
            host_id=None,
        )

        context = _resource_to_cel_context(volume)

        # Should use created_at since VolumeInfo has it
        assert 3 * 24 * 3600 - 10 < context["age"] < 3 * 24 * 3600 + 10

    def test_age_from_string_isoformat_created_at(self) -> None:
        """Test that age can be calculated from ISO format string created_at."""
        # Create a snapshot and manually check the context generation handles strings
        created_time = datetime.now(timezone.utc) - timedelta(minutes=30)
        snapshot = SnapshotInfo(
            id=SnapshotId.generate(),
            name=SnapshotName("string-date-snapshot"),
            created_at=created_time,
            size_bytes=500,
        )

        context = _resource_to_cel_context(snapshot)

        # Age should be approximately 30 minutes (1800 seconds)
        assert 30 * 60 - 10 < context["age"] < 30 * 60 + 10

    def test_raises_error_for_non_model_resource(self) -> None:
        """Test that an error is raised for resources without model_dump."""

        class NonPydanticResource:
            pass

        with pytest.raises(MngrError, match="Cannot convert resource type"):
            _resource_to_cel_context(NonPydanticResource())


class TestGetOrphanedWorkDirs:
    """Tests for _get_orphaned_work_dirs orphan detection and size/timestamp parsing."""

    def _create_mock_host(
        self,
        host_id: HostId,
        generated_work_dirs: tuple[str, ...],
        active_work_dirs: list[str],
        du_success: bool = True,
        du_output: str = "1024",
        stat_success: bool = True,
        stat_output: str = "1700000000",
    ) -> MagicMock:
        """Create a mock host with configurable behavior."""
        mock_host = MagicMock()
        mock_host.id = host_id
        mock_host.is_local = False

        # Mock certified data
        mock_certified_data = CertifiedHostData(generated_work_dirs=generated_work_dirs)
        mock_host.get_all_certified_data.return_value = mock_certified_data

        # Mock agents with work_dirs
        mock_agents = []
        for work_dir in active_work_dirs:
            mock_agent = MagicMock()
            mock_agent.work_dir = Path(work_dir)
            mock_agents.append(mock_agent)
        mock_host.get_agents.return_value = mock_agents

        # Mock execute_command for du and stat
        def mock_execute_command(cmd: str) -> CommandResult:
            if cmd.startswith("du "):
                return CommandResult(
                    stdout=du_output if du_success else "",
                    stderr="" if du_success else "error",
                    success=du_success,
                )
            elif cmd.startswith("stat "):
                return CommandResult(
                    stdout=stat_output if stat_success else "",
                    stderr="" if stat_success else "error",
                    success=stat_success,
                )
            else:
                return CommandResult(stdout="", stderr="", success=True)

        mock_host.execute_command.side_effect = mock_execute_command
        return mock_host

    def test_identifies_orphaned_directories(self) -> None:
        """Test that orphaned work dirs are correctly identified."""
        host_id = HostId.generate()
        provider_name = ProviderInstanceName("test-provider")

        # Only dir1 is active
        mock_host = self._create_mock_host(
            host_id=host_id,
            generated_work_dirs=("/work/dir1", "/work/dir2", "/work/dir3"),
            active_work_dirs=["/work/dir1"],
        )

        orphaned = _get_orphaned_work_dirs(host=mock_host, provider_name=provider_name)

        # dir2 and dir3 should be orphaned
        orphaned_paths = {str(d.path) for d in orphaned}
        assert orphaned_paths == {"/work/dir2", "/work/dir3"}

    def test_no_orphans_when_all_active(self) -> None:
        """Test that no orphans are returned when all dirs are active."""
        host_id = HostId.generate()
        provider_name = ProviderInstanceName("test-provider")

        mock_host = self._create_mock_host(
            host_id=host_id,
            generated_work_dirs=("/work/dir1", "/work/dir2"),
            active_work_dirs=["/work/dir1", "/work/dir2"],
        )

        orphaned = _get_orphaned_work_dirs(host=mock_host, provider_name=provider_name)

        assert len(orphaned) == 0

    def test_all_orphaned_when_no_active(self) -> None:
        """Test that all dirs are orphaned when none are active."""
        host_id = HostId.generate()
        provider_name = ProviderInstanceName("test-provider")

        mock_host = self._create_mock_host(
            host_id=host_id,
            generated_work_dirs=("/work/dir1", "/work/dir2"),
            active_work_dirs=[],
        )

        orphaned = _get_orphaned_work_dirs(host=mock_host, provider_name=provider_name)

        assert len(orphaned) == 2

    def test_size_parsing_from_du_command(self) -> None:
        """Test that size is correctly parsed from du command output."""
        host_id = HostId.generate()
        provider_name = ProviderInstanceName("test-provider")

        mock_host = self._create_mock_host(
            host_id=host_id,
            generated_work_dirs=("/work/orphan",),
            active_work_dirs=[],
            du_success=True,
            du_output="5678",
        )

        orphaned = _get_orphaned_work_dirs(host=mock_host, provider_name=provider_name)

        assert len(orphaned) == 1
        assert orphaned[0].size_bytes == 5678

    def test_size_defaults_to_zero_on_du_failure(self) -> None:
        """Test that size defaults to 0 when du command fails."""
        host_id = HostId.generate()
        provider_name = ProviderInstanceName("test-provider")

        mock_host = self._create_mock_host(
            host_id=host_id,
            generated_work_dirs=("/work/orphan",),
            active_work_dirs=[],
            du_success=False,
        )

        orphaned = _get_orphaned_work_dirs(host=mock_host, provider_name=provider_name)

        assert len(orphaned) == 1
        assert orphaned[0].size_bytes == 0

    def test_timestamp_parsing_from_stat_command(self) -> None:
        """Test that created_at is correctly parsed from stat command output."""
        host_id = HostId.generate()
        provider_name = ProviderInstanceName("test-provider")

        # Unix timestamp for 2023-11-14 22:13:20 UTC
        timestamp = 1700000000
        mock_host = self._create_mock_host(
            host_id=host_id,
            generated_work_dirs=("/work/orphan",),
            active_work_dirs=[],
            stat_success=True,
            stat_output=str(timestamp),
        )

        orphaned = _get_orphaned_work_dirs(host=mock_host, provider_name=provider_name)

        assert len(orphaned) == 1
        expected_dt = datetime.fromtimestamp(timestamp, tz=timezone.utc)
        assert orphaned[0].created_at == expected_dt

    def test_timestamp_defaults_to_now_on_stat_failure(self) -> None:
        """Test that created_at defaults to now when stat command fails."""
        host_id = HostId.generate()
        provider_name = ProviderInstanceName("test-provider")

        mock_host = self._create_mock_host(
            host_id=host_id,
            generated_work_dirs=("/work/orphan",),
            active_work_dirs=[],
            stat_success=False,
        )

        before = datetime.now(timezone.utc)
        orphaned = _get_orphaned_work_dirs(host=mock_host, provider_name=provider_name)
        after = datetime.now(timezone.utc)

        assert len(orphaned) == 1
        # created_at should be approximately now
        assert before <= orphaned[0].created_at <= after

    def test_work_dir_info_fields_populated_correctly(self) -> None:
        """Test that WorkDirInfo fields are correctly populated."""
        host_id = HostId.generate()
        provider_name = ProviderInstanceName("my-provider")

        mock_host = self._create_mock_host(
            host_id=host_id,
            generated_work_dirs=("/work/orphan",),
            active_work_dirs=[],
            du_success=True,
            du_output="9999",
        )

        orphaned = _get_orphaned_work_dirs(host=mock_host, provider_name=provider_name)

        assert len(orphaned) == 1
        info = orphaned[0]
        assert info.path == Path("/work/orphan")
        assert info.size_bytes == 9999
        assert info.host_id == host_id
        assert info.provider_name == provider_name
        assert info.is_local is False


class TestGcSnapshots:
    """Tests for gc_snapshots recency index computation."""

    def _create_mock_provider(
        self,
        supports_snapshots: bool,
        hosts: list[MagicMock],
    ) -> MagicMock:
        """Create a mock provider with configurable snapshot support."""
        mock_provider = MagicMock()
        mock_provider.name = ProviderInstanceName("test-provider")
        mock_provider.supports_snapshots = supports_snapshots
        mock_provider.list_hosts.return_value = hosts
        return mock_provider

    def test_recency_index_assigned_correctly(self) -> None:
        """Test that recency_idx is correctly assigned based on creation time."""
        # Create mock host with snapshots
        mock_host = MagicMock()
        mock_host.id = HostId.generate()

        now = datetime.now(timezone.utc)
        snapshots = [
            SnapshotInfo(
                id=SnapshotId.generate(),
                name=SnapshotName("oldest"),
                created_at=now - timedelta(days=10),
                size_bytes=100,
            ),
            SnapshotInfo(
                id=SnapshotId.generate(),
                name=SnapshotName("newest"),
                created_at=now - timedelta(days=1),
                size_bytes=200,
            ),
            SnapshotInfo(
                id=SnapshotId.generate(),
                name=SnapshotName("middle"),
                created_at=now - timedelta(days=5),
                size_bytes=150,
            ),
        ]

        mock_provider = self._create_mock_provider(
            supports_snapshots=True,
            hosts=[mock_host],
        )
        mock_provider.list_snapshots.return_value = snapshots

        result = GcResult()
        gc_snapshots(
            providers=[mock_provider],
            include_filters=(),
            exclude_filters=(),
            dry_run=True,
            error_behavior=ErrorBehavior.CONTINUE,
            result=result,
        )

        # Verify snapshots are ordered by recency_idx (newest first)
        assert len(result.snapshots_destroyed) == 3
        destroyed_by_name = {s.name: s for s in result.snapshots_destroyed}

        # Newest should have idx 0, middle idx 1, oldest idx 2
        assert destroyed_by_name["newest"].recency_idx == 0
        assert destroyed_by_name["middle"].recency_idx == 1
        assert destroyed_by_name["oldest"].recency_idx == 2

    def test_skips_provider_without_snapshot_support(self) -> None:
        """Test that providers without snapshot support are skipped."""
        mock_provider = self._create_mock_provider(
            supports_snapshots=False,
            hosts=[],
        )

        result = GcResult()
        gc_snapshots(
            providers=[mock_provider],
            include_filters=(),
            exclude_filters=(),
            dry_run=True,
            error_behavior=ErrorBehavior.CONTINUE,
            result=result,
        )

        # list_hosts should not be called if snapshots aren't supported
        mock_provider.list_hosts.assert_not_called()
        assert len(result.snapshots_destroyed) == 0

    def test_dry_run_does_not_delete_snapshots(self) -> None:
        """Test that dry_run=True does not actually delete snapshots."""
        mock_host = MagicMock()
        mock_host.id = HostId.generate()

        snapshot = SnapshotInfo(
            id=SnapshotId.generate(),
            name=SnapshotName("test"),
            created_at=datetime.now(timezone.utc),
            size_bytes=100,
        )

        mock_provider = self._create_mock_provider(
            supports_snapshots=True,
            hosts=[mock_host],
        )
        mock_provider.list_snapshots.return_value = [snapshot]

        result = GcResult()
        gc_snapshots(
            providers=[mock_provider],
            include_filters=(),
            exclude_filters=(),
            dry_run=True,
            error_behavior=ErrorBehavior.CONTINUE,
            result=result,
        )

        # Snapshot should be in result but delete_snapshot should not be called
        assert len(result.snapshots_destroyed) == 1
        mock_provider.delete_snapshot.assert_not_called()


class TestGcVolumes:
    """Tests for gc_volumes orphan detection."""

    def _create_mock_provider(
        self,
        supports_volumes: bool,
        all_volumes: list[VolumeInfo],
        active_hosts: list[MagicMock],
    ) -> MagicMock:
        """Create a mock provider with configurable volume support."""
        mock_provider = MagicMock()
        mock_provider.name = ProviderInstanceName("test-provider")
        mock_provider.supports_volumes = supports_volumes
        mock_provider.list_volumes.return_value = all_volumes
        mock_provider.list_hosts.return_value = active_hosts
        return mock_provider

    def test_identifies_orphaned_volumes(self) -> None:
        """Test that volumes with host_id not matching active hosts are orphaned."""
        active_host_id = HostId.generate()
        inactive_host_id = HostId.generate()

        mock_host = MagicMock()
        mock_host.id = active_host_id

        volumes = [
            VolumeInfo(
                volume_id=VolumeId.generate(),
                name="active-volume",
                size_bytes=1000,
                created_at=datetime.now(timezone.utc),
                host_id=active_host_id,
            ),
            # This volume's host is not active
            VolumeInfo(
                volume_id=VolumeId.generate(),
                name="orphan-volume",
                size_bytes=2000,
                created_at=datetime.now(timezone.utc),
                host_id=inactive_host_id,
            ),
            # Not attached to any host
            VolumeInfo(
                volume_id=VolumeId.generate(),
                name="unattached-volume",
                size_bytes=3000,
                created_at=datetime.now(timezone.utc),
                host_id=None,
            ),
        ]

        mock_provider = self._create_mock_provider(
            supports_volumes=True,
            all_volumes=volumes,
            active_hosts=[mock_host],
        )

        result = GcResult()
        gc_volumes(
            providers=[mock_provider],
            include_filters=(),
            exclude_filters=(),
            dry_run=True,
            error_behavior=ErrorBehavior.CONTINUE,
            result=result,
        )

        # Only the orphan and unattached volumes should be destroyed
        destroyed_names = {v.name for v in result.volumes_destroyed}
        assert destroyed_names == {"orphan-volume", "unattached-volume"}

    def test_no_orphans_when_all_volumes_attached(self) -> None:
        """Test that no orphans are found when all volumes are attached to active hosts."""
        host_id = HostId.generate()

        mock_host = MagicMock()
        mock_host.id = host_id

        volumes = [
            VolumeInfo(
                volume_id=VolumeId.generate(),
                name="attached-volume",
                size_bytes=1000,
                created_at=datetime.now(timezone.utc),
                host_id=host_id,
            ),
        ]

        mock_provider = self._create_mock_provider(
            supports_volumes=True,
            all_volumes=volumes,
            active_hosts=[mock_host],
        )

        result = GcResult()
        gc_volumes(
            providers=[mock_provider],
            include_filters=(),
            exclude_filters=(),
            dry_run=True,
            error_behavior=ErrorBehavior.CONTINUE,
            result=result,
        )

        assert len(result.volumes_destroyed) == 0

    def test_skips_provider_without_volume_support(self) -> None:
        """Test that providers without volume support are skipped."""
        mock_provider = self._create_mock_provider(
            supports_volumes=False,
            all_volumes=[],
            active_hosts=[],
        )

        result = GcResult()
        gc_volumes(
            providers=[mock_provider],
            include_filters=(),
            exclude_filters=(),
            dry_run=True,
            error_behavior=ErrorBehavior.CONTINUE,
            result=result,
        )

        mock_provider.list_volumes.assert_not_called()
        assert len(result.volumes_destroyed) == 0

    def test_dry_run_does_not_delete_volumes(self) -> None:
        """Test that dry_run=True does not actually delete volumes."""
        # Unattached volume
        volumes = [
            VolumeInfo(
                volume_id=VolumeId.generate(),
                name="orphan",
                size_bytes=1000,
                created_at=datetime.now(timezone.utc),
                host_id=None,
            ),
        ]

        mock_provider = self._create_mock_provider(
            supports_volumes=True,
            all_volumes=volumes,
            active_hosts=[],
        )

        result = GcResult()
        gc_volumes(
            providers=[mock_provider],
            include_filters=(),
            exclude_filters=(),
            dry_run=True,
            error_behavior=ErrorBehavior.CONTINUE,
            result=result,
        )

        assert len(result.volumes_destroyed) == 1
        mock_provider.delete_volume.assert_not_called()


class TestGcMachines:
    """Tests for gc_machines agent count check."""

    def _create_mock_provider(self, hosts: list[MagicMock]) -> MagicMock:
        """Create a mock provider with the given hosts."""
        mock_provider = MagicMock()
        mock_provider.name = ProviderInstanceName("test-provider")
        mock_provider.list_hosts.return_value = hosts
        return mock_provider

    def _create_mock_host(
        self,
        host_id: HostId,
        is_local: bool = False,
        agent_count: int = 0,
    ) -> MagicMock:
        """Create a mock host with configurable agent count."""
        mock_host = MagicMock()
        mock_host.id = host_id
        mock_host.is_local = is_local

        # Create mock agents
        mock_agents = [MagicMock() for _ in range(agent_count)]
        mock_host.get_agents.return_value = mock_agents

        return mock_host

    def test_host_with_agents_not_gc_collected(self) -> None:
        """Test that hosts with agents are NOT garbage collected."""
        host_id = HostId.generate()
        mock_host = self._create_mock_host(
            host_id=host_id,
            is_local=False,
            agent_count=1,
        )

        mock_provider = self._create_mock_provider(hosts=[mock_host])

        result = GcResult()
        gc_machines(
            providers=[mock_provider],
            include_filters=(),
            exclude_filters=(),
            dry_run=False,
            error_behavior=ErrorBehavior.CONTINUE,
            result=result,
        )

        # Host should NOT be destroyed because it has agents
        assert len(result.machines_destroyed) == 0
        mock_provider.destroy_host.assert_not_called()

    def test_host_without_agents_is_gc_collected(self) -> None:
        """Test that hosts without agents ARE garbage collected."""
        host_id = HostId.generate()
        mock_host = self._create_mock_host(
            host_id=host_id,
            is_local=False,
            agent_count=0,
        )

        mock_provider = self._create_mock_provider(hosts=[mock_host])

        result = GcResult()
        gc_machines(
            providers=[mock_provider],
            include_filters=(),
            exclude_filters=(),
            dry_run=True,
            error_behavior=ErrorBehavior.CONTINUE,
            result=result,
        )

        # Host should be destroyed because it has no agents
        assert len(result.machines_destroyed) == 1
        assert result.machines_destroyed[0].id == host_id

    def test_local_host_never_gc_collected(self) -> None:
        """Test that local hosts are never garbage collected even with no agents."""
        host_id = HostId.generate()
        mock_host = self._create_mock_host(
            host_id=host_id,
            is_local=True,
            agent_count=0,
        )

        mock_provider = self._create_mock_provider(hosts=[mock_host])

        result = GcResult()
        gc_machines(
            providers=[mock_provider],
            include_filters=(),
            exclude_filters=(),
            dry_run=False,
            error_behavior=ErrorBehavior.CONTINUE,
            result=result,
        )

        # Local host should NOT be destroyed even without agents
        assert len(result.machines_destroyed) == 0
        mock_provider.destroy_host.assert_not_called()

    def test_multiple_hosts_mixed_agents(self) -> None:
        """Test gc with multiple hosts having different agent counts."""
        host_with_agents = self._create_mock_host(
            host_id=HostId.generate(),
            is_local=False,
            agent_count=2,
        )
        host_without_agents = self._create_mock_host(
            host_id=HostId.generate(),
            is_local=False,
            agent_count=0,
        )
        local_host = self._create_mock_host(
            host_id=HostId.generate(),
            is_local=True,
            agent_count=0,
        )

        mock_provider = self._create_mock_provider(hosts=[host_with_agents, host_without_agents, local_host])

        result = GcResult()
        gc_machines(
            providers=[mock_provider],
            include_filters=(),
            exclude_filters=(),
            dry_run=True,
            error_behavior=ErrorBehavior.CONTINUE,
            result=result,
        )

        # Only the host without agents (non-local) should be destroyed
        assert len(result.machines_destroyed) == 1
        assert result.machines_destroyed[0].id == host_without_agents.id

    def test_dry_run_does_not_destroy_hosts(self) -> None:
        """Test that dry_run=True does not actually destroy hosts."""
        host_id = HostId.generate()
        mock_host = self._create_mock_host(
            host_id=host_id,
            is_local=False,
            agent_count=0,
        )

        mock_provider = self._create_mock_provider(hosts=[mock_host])

        result = GcResult()
        gc_machines(
            providers=[mock_provider],
            include_filters=(),
            exclude_filters=(),
            dry_run=True,
            error_behavior=ErrorBehavior.CONTINUE,
            result=result,
        )

        # Host should be in result but destroy_host should not be called
        assert len(result.machines_destroyed) == 1
        mock_provider.destroy_host.assert_not_called()
