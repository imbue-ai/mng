import subprocess
from pathlib import Path
from typing import cast

import pytest

from imbue.concurrency_group.concurrency_group import ConcurrencyGroup
from imbue.mngr.api.pair import UnisonSyncer
from imbue.mngr.api.pair import determine_git_sync_actions
from imbue.mngr.api.pair import pair_files
from imbue.mngr.api.pair import sync_git_state
from imbue.mngr.api.test_fixtures import FakeAgent
from imbue.mngr.api.test_fixtures import FakeHost
from imbue.mngr.api.test_fixtures import SyncTestContext
from imbue.mngr.errors import MngrError
from imbue.mngr.errors import UnisonNotInstalledError
from imbue.mngr.interfaces.agent import AgentInterface
from imbue.mngr.interfaces.host import OnlineHostInterface
from imbue.mngr.primitives import ConflictMode
from imbue.mngr.primitives import SyncDirection
from imbue.mngr.primitives import UncommittedChangesMode
from imbue.mngr.utils.polling import wait_for
from imbue.mngr.utils.testing import init_git_repo_with_config
from imbue.mngr.utils.testing import run_git_command


@pytest.fixture
def pair_ctx(tmp_path: Path) -> SyncTestContext:
    """Create a test context with agent and local directories as git repos."""
    agent_dir = tmp_path / "source"
    local_dir = tmp_path / "target"
    init_git_repo_with_config(agent_dir)
    subprocess.run(["git", "clone", str(agent_dir), str(local_dir)], capture_output=True, check=True)
    run_git_command(local_dir, "config", "user.email", "test@example.com")
    run_git_command(local_dir, "config", "user.name", "Test User")
    return SyncTestContext(
        agent_dir=agent_dir,
        local_dir=local_dir,
        agent=cast(AgentInterface, FakeAgent(work_dir=agent_dir)),
        host=cast(OnlineHostInterface, FakeHost()),
    )


def test_sync_git_state_performs_push_when_local_is_ahead(cg: ConcurrencyGroup, pair_ctx: SyncTestContext) -> None:
    (pair_ctx.local_dir / "new_file.txt").write_text("new content")
    run_git_command(pair_ctx.local_dir, "add", "new_file.txt")
    run_git_command(pair_ctx.local_dir, "commit", "-m", "Add new file")
    git_action = determine_git_sync_actions(cg, pair_ctx.agent_dir, pair_ctx.local_dir)
    assert git_action is not None
    assert git_action.local_is_ahead is True
    git_pull_performed, git_push_performed = sync_git_state(
        cg=cg,
        agent=pair_ctx.agent,
        host=pair_ctx.host,
        local_path=pair_ctx.local_dir,
        git_sync_action=git_action,
        uncommitted_changes=UncommittedChangesMode.CLOBBER,
    )
    assert git_push_performed is True
    assert git_pull_performed is False
    assert (pair_ctx.agent_dir / "new_file.txt").exists()


def test_sync_git_state_performs_pull_when_agent_is_ahead(cg: ConcurrencyGroup, pair_ctx: SyncTestContext) -> None:
    (pair_ctx.agent_dir / "agent_file.txt").write_text("agent content")
    run_git_command(pair_ctx.agent_dir, "add", "agent_file.txt")
    run_git_command(pair_ctx.agent_dir, "commit", "-m", "Add agent file")
    git_action = determine_git_sync_actions(cg, pair_ctx.agent_dir, pair_ctx.local_dir)
    assert git_action is not None
    assert git_action.agent_is_ahead is True
    git_pull_performed, git_push_performed = sync_git_state(
        cg=cg,
        agent=pair_ctx.agent,
        host=pair_ctx.host,
        local_path=pair_ctx.local_dir,
        git_sync_action=git_action,
        uncommitted_changes=UncommittedChangesMode.CLOBBER,
    )
    assert git_pull_performed is True
    assert git_push_performed is False
    assert (pair_ctx.local_dir / "agent_file.txt").exists()


def test_pair_files_raises_when_unison_not_installed_and_mocked(
    cg: ConcurrencyGroup, pair_ctx: SyncTestContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("imbue.mngr.api.pair.check_unison_installed", lambda: False)
    with pytest.raises(UnisonNotInstalledError):
        with pair_files(
            cg=cg,
            agent=pair_ctx.agent,
            host=pair_ctx.host,
            agent_path=pair_ctx.agent_dir,
            local_path=pair_ctx.local_dir,
            sync_direction=SyncDirection.BOTH,
            conflict_mode=ConflictMode.NEWER,
            is_require_git=False,
            uncommitted_changes=UncommittedChangesMode.FAIL,
            exclude_patterns=(),
            include_patterns=(),
        ):
            pass


def test_pair_files_raises_when_git_required_but_not_present(
    cg: ConcurrencyGroup, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("imbue.mngr.api.pair.check_unison_installed", lambda: True)
    source_dir = tmp_path / "source"
    target_dir = tmp_path / "target"
    source_dir.mkdir()
    target_dir.mkdir()
    agent = cast(AgentInterface, FakeAgent(work_dir=source_dir))
    host = cast(OnlineHostInterface, FakeHost())
    with pytest.raises(MngrError) as exc_info:
        with pair_files(
            cg=cg,
            agent=agent,
            host=host,
            agent_path=source_dir,
            local_path=target_dir,
            sync_direction=SyncDirection.BOTH,
            conflict_mode=ConflictMode.NEWER,
            is_require_git=True,
            uncommitted_changes=UncommittedChangesMode.FAIL,
            exclude_patterns=(),
            include_patterns=(),
        ):
            pass
    assert "Git repositories required" in str(exc_info.value)


def test_pair_files_starts_and_stops_syncer(cg: ConcurrencyGroup, pair_ctx: SyncTestContext) -> None:
    with pair_files(
        cg=cg,
        agent=pair_ctx.agent,
        host=pair_ctx.host,
        agent_path=pair_ctx.agent_dir,
        local_path=pair_ctx.local_dir,
        sync_direction=SyncDirection.BOTH,
        conflict_mode=ConflictMode.NEWER,
        is_require_git=True,
        uncommitted_changes=UncommittedChangesMode.CLOBBER,
        exclude_patterns=(),
        include_patterns=(),
    ) as syncer:
        wait_for(lambda: syncer.is_running, error_message="Syncer did not start within timeout")
        assert syncer.is_running is True
        syncer.stop()
        wait_for(lambda: not syncer.is_running, error_message="Syncer did not stop within timeout")
        assert syncer.is_running is False


def test_pair_files_syncs_git_state_before_starting(cg: ConcurrencyGroup, pair_ctx: SyncTestContext) -> None:
    (pair_ctx.agent_dir / "agent_commit.txt").write_text("agent content")
    run_git_command(pair_ctx.agent_dir, "add", "agent_commit.txt")
    run_git_command(pair_ctx.agent_dir, "commit", "-m", "Add agent commit")
    assert not (pair_ctx.local_dir / "agent_commit.txt").exists()
    with pair_files(
        cg=cg,
        agent=pair_ctx.agent,
        host=pair_ctx.host,
        agent_path=pair_ctx.agent_dir,
        local_path=pair_ctx.local_dir,
        sync_direction=SyncDirection.BOTH,
        conflict_mode=ConflictMode.NEWER,
        is_require_git=True,
        uncommitted_changes=UncommittedChangesMode.CLOBBER,
        exclude_patterns=(),
        include_patterns=(),
    ) as syncer:
        assert (pair_ctx.local_dir / "agent_commit.txt").exists()
        syncer.stop()


def test_pair_files_with_no_git_requirement(cg: ConcurrencyGroup, tmp_path: Path) -> None:
    source_dir = tmp_path / "source"
    target_dir = tmp_path / "target"
    source_dir.mkdir()
    target_dir.mkdir()
    (source_dir / "test_file.txt").write_text("test content")
    agent = cast(AgentInterface, FakeAgent(work_dir=source_dir))
    host = cast(OnlineHostInterface, FakeHost())
    with pair_files(
        cg=cg,
        agent=agent,
        host=host,
        agent_path=source_dir,
        local_path=target_dir,
        sync_direction=SyncDirection.BOTH,
        conflict_mode=ConflictMode.NEWER,
        is_require_git=False,
        uncommitted_changes=UncommittedChangesMode.FAIL,
        exclude_patterns=(),
        include_patterns=(),
    ) as syncer:
        wait_for(lambda: syncer.is_running, error_message="Syncer did not start within timeout")
        assert syncer.is_running is True
        syncer.stop()


def test_unison_syncer_start_and_stop(cg: ConcurrencyGroup, tmp_path: Path) -> None:
    source = tmp_path / "source"
    target = tmp_path / "target"
    source.mkdir()
    target.mkdir()
    syncer = UnisonSyncer(
        cg=cg,
        source_path=source,
        target_path=target,
        sync_direction=SyncDirection.BOTH,
        conflict_mode=ConflictMode.NEWER,
    )
    try:
        syncer.start()
        wait_for(lambda: syncer.is_running, error_message="Syncer did not start within timeout")
        assert syncer.is_running is True
    finally:
        syncer.stop()
    wait_for(lambda: not syncer.is_running, timeout=5.0, error_message="Syncer did not stop within timeout")
    assert syncer.is_running is False


def test_unison_syncer_syncs_file_changes(cg: ConcurrencyGroup, tmp_path: Path) -> None:
    source = tmp_path / "source"
    target = tmp_path / "target"
    source.mkdir()
    target.mkdir()
    (source / "initial.txt").write_text("initial content")
    syncer = UnisonSyncer(
        cg=cg,
        source_path=source,
        target_path=target,
        sync_direction=SyncDirection.BOTH,
        conflict_mode=ConflictMode.NEWER,
    )
    try:
        syncer.start()
        wait_for(lambda: (target / "initial.txt").exists(), error_message="File was not synced within timeout")
        assert (target / "initial.txt").exists()
        assert (target / "initial.txt").read_text() == "initial content"
    finally:
        syncer.stop()


def test_unison_syncer_syncs_symlinks(cg: ConcurrencyGroup, tmp_path: Path) -> None:
    source = tmp_path / "source"
    target = tmp_path / "target"
    source.mkdir()
    target.mkdir()
    (source / "real_file.txt").write_text("real content")
    (source / "link_to_file.txt").symlink_to(source / "real_file.txt")
    syncer = UnisonSyncer(
        cg=cg,
        source_path=source,
        target_path=target,
        sync_direction=SyncDirection.BOTH,
        conflict_mode=ConflictMode.NEWER,
    )
    try:
        syncer.start()
        wait_for(lambda: (target / "link_to_file.txt").exists(), error_message="Symlink was not synced within timeout")
        assert (target / "real_file.txt").exists()
        assert (target / "link_to_file.txt").exists()
        assert (target / "link_to_file.txt").is_symlink()
    finally:
        syncer.stop()


def test_unison_syncer_syncs_directory_symlinks(cg: ConcurrencyGroup, tmp_path: Path) -> None:
    source = tmp_path / "source"
    target = tmp_path / "target"
    source.mkdir()
    target.mkdir()
    (source / "real_dir").mkdir()
    (source / "real_dir" / "file.txt").write_text("content in dir")
    (source / "link_to_dir").symlink_to(source / "real_dir")
    syncer = UnisonSyncer(
        cg=cg,
        source_path=source,
        target_path=target,
        sync_direction=SyncDirection.BOTH,
        conflict_mode=ConflictMode.NEWER,
    )
    try:
        syncer.start()
        wait_for(
            lambda: (target / "link_to_dir").exists(), error_message="Directory symlink was not synced within timeout"
        )
        assert (target / "real_dir").exists()
        assert (target / "real_dir").is_dir()
        assert (target / "link_to_dir").exists()
        assert (target / "link_to_dir").is_symlink()
    finally:
        syncer.stop()


def test_unison_syncer_handles_process_crash(cg: ConcurrencyGroup, tmp_path: Path) -> None:
    source = tmp_path / "source"
    target = tmp_path / "target"
    source.mkdir()
    target.mkdir()
    syncer = UnisonSyncer(
        cg=cg,
        source_path=source,
        target_path=target,
        sync_direction=SyncDirection.BOTH,
        conflict_mode=ConflictMode.NEWER,
    )
    try:
        syncer.start()
        wait_for(lambda: syncer.is_running, error_message="Syncer did not start within timeout")
        assert syncer.is_running is True
        assert syncer._running_process is not None
        # Simulate a hard crash by directly setting the shutdown event, bypassing
        # the syncer's stop() method. This causes the underlying process to be
        # killed unexpectedly from the syncer's perspective.
        syncer._running_process._shutdown_event.set()
        wait_for(lambda: not syncer.is_running, error_message="Syncer did not detect process crash")
        assert syncer.is_running is False
    finally:
        syncer.stop()


@pytest.mark.release
def test_unison_syncer_handles_large_files(cg: ConcurrencyGroup, tmp_path: Path) -> None:
    source = tmp_path / "source"
    target = tmp_path / "target"
    source.mkdir()
    target.mkdir()
    large_file = source / "large_file.bin"
    chunk_size = 1024 * 1024
    total_size = 50 * chunk_size
    with open(large_file, "wb") as f:
        for i in range(50):
            chunk = bytes([i % 256] * chunk_size)
            f.write(chunk)
    assert large_file.stat().st_size == total_size
    syncer = UnisonSyncer(
        cg=cg,
        source_path=source,
        target_path=target,
        sync_direction=SyncDirection.BOTH,
        conflict_mode=ConflictMode.NEWER,
    )
    try:
        syncer.start()
        wait_for(
            lambda: (target / "large_file.bin").exists() and (target / "large_file.bin").stat().st_size == total_size,
            timeout=60.0,
            error_message="Large file was not synced within timeout",
        )
        assert (target / "large_file.bin").stat().st_size == total_size
        with open(target / "large_file.bin", "rb") as f:
            first_chunk = f.read(chunk_size)
            assert first_chunk == bytes([0] * chunk_size)
            f.seek(-chunk_size, 2)
            last_chunk = f.read(chunk_size)
            assert last_chunk == bytes([49 % 256] * chunk_size)
    finally:
        syncer.stop()
