"""Tests for the LocalProviderInstance."""

import json
import tempfile
from pathlib import Path
from uuid import uuid4

import pytest

from imbue.mngr.config.data_types import MngrConfig
from imbue.mngr.config.data_types import PROFILES_DIRNAME
from imbue.mngr.errors import HostNotFoundError
from imbue.mngr.errors import LocalHostNotDestroyableError
from imbue.mngr.errors import LocalHostNotStoppableError
from imbue.mngr.errors import SnapshotsNotSupportedError
from imbue.mngr.primitives import HostId
from imbue.mngr.primitives import HostName
from imbue.mngr.primitives import LOCAL_PROVIDER_NAME
from imbue.mngr.primitives import SnapshotId
from imbue.mngr.providers.local.instance import LocalProviderInstance
from imbue.mngr.utils.testing import make_local_provider


def test_local_provider_name(local_provider: LocalProviderInstance) -> None:
    assert local_provider.name == LOCAL_PROVIDER_NAME


def test_local_provider_does_not_support_snapshots(local_provider: LocalProviderInstance) -> None:
    assert local_provider.supports_snapshots is False


def test_local_provider_supports_mutable_tags(local_provider: LocalProviderInstance) -> None:
    assert local_provider.supports_mutable_tags is True


def test_create_host_returns_host_with_persistent_id(temp_host_dir: Path, temp_config: MngrConfig) -> None:
    # Use the same profile_dir for both providers to test persistence
    profile_dir = temp_host_dir / PROFILES_DIRNAME / uuid4().hex
    provider1 = make_local_provider(temp_host_dir, temp_config, profile_dir=profile_dir)
    provider2 = make_local_provider(temp_host_dir, temp_config, profile_dir=profile_dir)

    host1 = provider1.create_host(HostName("test"))
    host2 = provider2.create_host(HostName("test"))

    assert host1.id == host2.id


def test_create_host_generates_new_id_for_different_dirs(mngr_test_prefix: str) -> None:
    with tempfile.TemporaryDirectory() as tmpdir1:
        with tempfile.TemporaryDirectory() as tmpdir2:
            config1 = MngrConfig(default_host_dir=Path(tmpdir1), prefix=mngr_test_prefix)
            config2 = MngrConfig(default_host_dir=Path(tmpdir2), prefix=mngr_test_prefix)
            provider1 = make_local_provider(Path(tmpdir1), config1)
            provider2 = make_local_provider(Path(tmpdir2), config2)

            host1 = provider1.create_host(HostName("test"))
            host2 = provider2.create_host(HostName("test"))

            assert host1.id != host2.id


def test_host_id_persists_across_provider_instances(temp_host_dir: Path, temp_config: MngrConfig) -> None:
    # Use the same profile_dir for both providers to test persistence
    profile_dir = temp_host_dir / PROFILES_DIRNAME / uuid4().hex
    provider1 = make_local_provider(temp_host_dir, temp_config, profile_dir=profile_dir)
    host1 = provider1.create_host(HostName("test"))
    host_id = host1.id

    provider2 = make_local_provider(temp_host_dir, temp_config, profile_dir=profile_dir)
    host2 = provider2.create_host(HostName("test"))

    assert host2.id == host_id

    # host_id is stored globally in default_host_dir (not per-profile)
    # because it identifies the local machine, not a profile
    host_id_path = temp_host_dir / "host_id"
    assert host_id_path.exists()
    assert host_id_path.read_text().strip() == host_id


def test_stop_host_raises_error(local_provider: LocalProviderInstance) -> None:
    host = local_provider.create_host(HostName("test"))
    with pytest.raises(LocalHostNotStoppableError):
        local_provider.stop_host(host)


def test_destroy_host_raises_error(local_provider: LocalProviderInstance) -> None:
    host = local_provider.create_host(HostName("test"))
    with pytest.raises(LocalHostNotDestroyableError):
        local_provider.destroy_host(host)


def test_start_host_returns_host(local_provider: LocalProviderInstance) -> None:
    host1 = local_provider.create_host(HostName("test"))
    host2 = local_provider.start_host(host1)

    assert host2.id == host1.id


def test_get_host_by_id(local_provider: LocalProviderInstance) -> None:
    host1 = local_provider.create_host(HostName("test"))
    host2 = local_provider.get_host(host1.id)

    assert host2.id == host1.id


def test_get_host_by_name(local_provider: LocalProviderInstance) -> None:
    host1 = local_provider.create_host(HostName("test"))
    host2 = local_provider.get_host(HostName("local"))

    assert host2.id == host1.id


def test_get_host_with_wrong_id_raises_error(local_provider: LocalProviderInstance) -> None:
    local_provider.create_host(HostName("test"))
    wrong_id = HostId.generate()

    with pytest.raises(HostNotFoundError) as exc_info:
        local_provider.get_host(wrong_id)

    assert exc_info.value.host == wrong_id


def test_list_hosts_returns_single_host(local_provider: LocalProviderInstance) -> None:
    hosts = local_provider.list_hosts()
    assert len(hosts) == 1


def test_create_snapshot_raises_error(local_provider: LocalProviderInstance) -> None:
    host = local_provider.create_host(HostName("test"))
    with pytest.raises(SnapshotsNotSupportedError) as exc_info:
        local_provider.create_snapshot(host)

    assert exc_info.value.provider_name == LOCAL_PROVIDER_NAME


def test_list_snapshots_returns_empty_list(local_provider: LocalProviderInstance) -> None:
    host = local_provider.create_host(HostName("test"))
    snapshots = local_provider.list_snapshots(host)
    assert snapshots == []


def test_delete_snapshot_raises_error(local_provider: LocalProviderInstance) -> None:
    host = local_provider.create_host(HostName("test"))
    with pytest.raises(SnapshotsNotSupportedError):
        local_provider.delete_snapshot(host, SnapshotId("snap-test"))


def test_get_host_tags_empty_by_default(local_provider: LocalProviderInstance) -> None:
    host = local_provider.create_host(HostName("test"))
    tags = local_provider.get_host_tags(host)
    assert tags == {}


def test_set_host_tags(local_provider: LocalProviderInstance) -> None:
    host = local_provider.create_host(HostName("test"))
    tags = {"env": "test", "team": "backend"}

    local_provider.set_host_tags(host, tags)

    retrieved_tags = local_provider.get_host_tags(host)
    assert len(retrieved_tags) == 2
    assert retrieved_tags["env"] == "test"
    assert retrieved_tags["team"] == "backend"


def test_add_tags_to_host(local_provider: LocalProviderInstance) -> None:
    host = local_provider.create_host(HostName("test"))
    local_provider.set_host_tags(host, {"env": "test"})

    local_provider.add_tags_to_host(host, {"team": "backend"})

    tags = local_provider.get_host_tags(host)
    assert len(tags) == 2
    assert tags["env"] == "test"
    assert tags["team"] == "backend"


def test_add_tags_updates_existing_tag(local_provider: LocalProviderInstance) -> None:
    host = local_provider.create_host(HostName("test"))
    local_provider.set_host_tags(host, {"env": "test"})

    local_provider.add_tags_to_host(host, {"env": "prod"})

    tags = local_provider.get_host_tags(host)
    assert len(tags) == 1
    assert tags["env"] == "prod"


def test_remove_tags_from_host(local_provider: LocalProviderInstance) -> None:
    host = local_provider.create_host(HostName("test"))
    local_provider.set_host_tags(host, {"env": "test", "team": "backend"})

    local_provider.remove_tags_from_host(host, ["env"])

    tags = local_provider.get_host_tags(host)
    assert len(tags) == 1
    assert tags["team"] == "backend"


def test_tags_persist_to_file(temp_host_dir: Path, temp_config: MngrConfig) -> None:
    profile_dir = temp_host_dir / PROFILES_DIRNAME / uuid4().hex
    provider = make_local_provider(temp_host_dir, temp_config, profile_dir=profile_dir)
    host = provider.create_host(HostName("test"))

    provider.set_host_tags(host, {"env": "test"})

    # Tags are stored in default_host_dir (not per-profile) since they're local machine data
    labels_path = temp_host_dir / "providers" / "local" / "labels.json"
    assert labels_path.exists()

    with open(labels_path) as f:
        data = json.load(f)

    assert len(data) == 1
    assert data[0]["key"] == "env"
    assert data[0]["value"] == "test"


def test_create_host_with_tags(local_provider: LocalProviderInstance) -> None:
    host = local_provider.create_host(HostName("test"), tags={"env": "test"})

    retrieved_tags = local_provider.get_host_tags(host)
    assert len(retrieved_tags) == 1
    assert retrieved_tags["env"] == "test"


def test_rename_host_returns_host_with_same_id(local_provider: LocalProviderInstance) -> None:
    host1 = local_provider.create_host(HostName("test"))
    host2 = local_provider.rename_host(host1, HostName("new_name"))

    assert host2.id == host1.id


def test_get_connector_returns_pyinfra_host(local_provider: LocalProviderInstance) -> None:
    host = local_provider.create_host(HostName("test"))
    connector = local_provider.get_connector(host)

    assert connector.name == "@local"


def test_get_host_resources_returns_valid_resources(local_provider: LocalProviderInstance) -> None:
    host = local_provider.create_host(HostName("test"))
    resources = local_provider.get_host_resources(host)

    assert resources.cpu.count >= 1
    assert resources.memory_gb >= 0


def test_host_has_local_connector(local_provider: LocalProviderInstance) -> None:
    host = local_provider.create_host(HostName("test"))
    assert host.connector.connector_cls_name == "LocalConnector"


def test_list_volumes_returns_empty_list(local_provider: LocalProviderInstance) -> None:
    """Local provider does not support volumes, should return empty list."""
    volumes = local_provider.list_volumes()
    assert volumes == []


def test_get_host_tags_returns_empty_when_labels_file_is_empty(temp_host_dir: Path, temp_config: MngrConfig) -> None:
    """get_host_tags should return empty dict when labels file exists but is empty."""
    profile_dir = temp_host_dir / PROFILES_DIRNAME / uuid4().hex
    provider = make_local_provider(temp_host_dir, temp_config, profile_dir=profile_dir)
    host = provider.create_host(HostName("test"))

    labels_path = profile_dir / "providers" / "local" / "labels.json"
    labels_path.parent.mkdir(parents=True, exist_ok=True)
    labels_path.write_text("")

    tags = provider.get_host_tags(host)
    assert tags == {}
