"""Unit tests for sync API functions."""

from pathlib import Path
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest

from imbue.mngr.api.sync import GitSyncError
from imbue.mngr.api.sync import LocalGitContext
from imbue.mngr.api.sync import NotAGitRepositoryError
from imbue.mngr.api.sync import RemoteGitContext
from imbue.mngr.api.sync import SyncFilesResult
from imbue.mngr.api.sync import SyncGitResult
from imbue.mngr.api.sync import SyncMode
from imbue.mngr.api.sync import UncommittedChangesError
from imbue.mngr.api.sync import handle_uncommitted_changes
from imbue.mngr.errors import MngrError
from imbue.mngr.primitives import UncommittedChangesMode

# =============================================================================
# SyncMode enum tests
# =============================================================================


def test_sync_mode_push_has_correct_value() -> None:
    assert SyncMode.PUSH.value == "PUSH"


def test_sync_mode_pull_has_correct_value() -> None:
    assert SyncMode.PULL.value == "PULL"


# =============================================================================
# SyncFilesResult model tests
# =============================================================================


def test_sync_files_result_can_be_created_with_all_fields() -> None:
    result = SyncFilesResult(
        files_transferred=10,
        bytes_transferred=1024,
        source_path=Path("/source"),
        destination_path=Path("/dest"),
        is_dry_run=False,
        mode=SyncMode.PUSH,
    )

    assert result.files_transferred == 10
    assert result.bytes_transferred == 1024
    assert result.source_path == Path("/source")
    assert result.destination_path == Path("/dest")
    assert result.is_dry_run is False
    assert result.mode == SyncMode.PUSH


def test_sync_files_result_supports_dry_run_mode() -> None:
    result = SyncFilesResult(
        files_transferred=5,
        bytes_transferred=0,
        source_path=Path("/source"),
        destination_path=Path("/dest"),
        is_dry_run=True,
        mode=SyncMode.PULL,
    )

    assert result.is_dry_run is True
    assert result.mode == SyncMode.PULL


def test_sync_files_result_can_be_serialized_to_dict() -> None:
    result = SyncFilesResult(
        files_transferred=3,
        bytes_transferred=500,
        source_path=Path("/src"),
        destination_path=Path("/dst"),
        is_dry_run=False,
        mode=SyncMode.PUSH,
    )

    data = result.model_dump()
    assert data["files_transferred"] == 3
    assert data["bytes_transferred"] == 500
    assert data["mode"] == SyncMode.PUSH


# =============================================================================
# SyncGitResult model tests
# =============================================================================


def test_sync_git_result_can_be_created_with_all_fields() -> None:
    result = SyncGitResult(
        source_branch="feature",
        target_branch="main",
        source_path=Path("/source"),
        destination_path=Path("/dest"),
        is_dry_run=False,
        commits_transferred=5,
        mode=SyncMode.PUSH,
    )

    assert result.source_branch == "feature"
    assert result.target_branch == "main"
    assert result.source_path == Path("/source")
    assert result.destination_path == Path("/dest")
    assert result.is_dry_run is False
    assert result.commits_transferred == 5
    assert result.mode == SyncMode.PUSH


def test_sync_git_result_supports_dry_run_mode() -> None:
    result = SyncGitResult(
        source_branch="dev",
        target_branch="main",
        source_path=Path("/src"),
        destination_path=Path("/dst"),
        is_dry_run=True,
        commits_transferred=0,
        mode=SyncMode.PULL,
    )

    assert result.is_dry_run is True
    assert result.mode == SyncMode.PULL


# =============================================================================
# UncommittedChangesError tests
# =============================================================================


def test_uncommitted_changes_error_contains_path_in_message() -> None:
    error = UncommittedChangesError(Path("/some/path"))
    assert "Uncommitted changes" in str(error)
    assert "/some/path" in str(error)


def test_uncommitted_changes_error_provides_user_help_text() -> None:
    error = UncommittedChangesError(Path("/some/path"))
    assert "stash" in error.user_help_text.lower()
    assert "clobber" in error.user_help_text.lower()


def test_uncommitted_changes_error_stores_destination_path() -> None:
    error = UncommittedChangesError(Path("/test/path"))
    assert error.destination == Path("/test/path")


# =============================================================================
# NotAGitRepositoryError tests
# =============================================================================


def test_not_a_git_repository_error_contains_path_in_message() -> None:
    error = NotAGitRepositoryError(Path("/not/a/repo"))
    assert "Not a git repository" in str(error)
    assert "/not/a/repo" in str(error)


def test_not_a_git_repository_error_provides_user_help_text() -> None:
    error = NotAGitRepositoryError(Path("/some/path"))
    assert "sync-mode=files" in error.user_help_text


def test_not_a_git_repository_error_stores_path() -> None:
    error = NotAGitRepositoryError(Path("/test/path"))
    assert error.path == Path("/test/path")


# =============================================================================
# GitSyncError tests
# =============================================================================


def test_git_sync_error_contains_message_in_str() -> None:
    error = GitSyncError("something went wrong")
    assert "Git sync failed" in str(error)
    assert "something went wrong" in str(error)


def test_git_sync_error_provides_user_help_text() -> None:
    error = GitSyncError("test")
    assert error.user_help_text is not None


# =============================================================================
# LocalGitContext tests
# =============================================================================


@patch("subprocess.run")
def test_local_git_context_has_uncommitted_changes_returns_true_when_changes_exist(
    mock_run: MagicMock,
) -> None:
    mock_run.return_value = MagicMock(returncode=0, stdout="M file.txt\n")
    ctx = LocalGitContext()
    assert ctx.has_uncommitted_changes(Path("/test")) is True


@patch("subprocess.run")
def test_local_git_context_has_uncommitted_changes_returns_false_when_clean(
    mock_run: MagicMock,
) -> None:
    mock_run.return_value = MagicMock(returncode=0, stdout="")
    ctx = LocalGitContext()
    assert ctx.has_uncommitted_changes(Path("/test")) is False


@patch("subprocess.run")
def test_local_git_context_has_uncommitted_changes_returns_false_on_error(
    mock_run: MagicMock,
) -> None:
    mock_run.return_value = MagicMock(returncode=1, stdout="")
    ctx = LocalGitContext()
    assert ctx.has_uncommitted_changes(Path("/test")) is False


@patch("subprocess.run")
def test_local_git_context_git_stash_returns_true_on_success(
    mock_run: MagicMock,
) -> None:
    mock_run.return_value = MagicMock(returncode=0, stdout="Saved working directory")
    ctx = LocalGitContext()
    result = ctx.git_stash(Path("/test"))
    assert result is True


@patch("subprocess.run")
def test_local_git_context_git_stash_returns_false_when_no_changes_to_save(
    mock_run: MagicMock,
) -> None:
    mock_run.return_value = MagicMock(returncode=0, stdout="No local changes to save")
    ctx = LocalGitContext()
    result = ctx.git_stash(Path("/test"))
    assert result is False


@patch("subprocess.run")
def test_local_git_context_git_stash_raises_on_failure(mock_run: MagicMock) -> None:
    mock_run.return_value = MagicMock(returncode=1, stderr="error")
    ctx = LocalGitContext()
    with pytest.raises(MngrError, match="git stash failed"):
        ctx.git_stash(Path("/test"))


@patch("subprocess.run")
def test_local_git_context_git_stash_pop_succeeds(mock_run: MagicMock) -> None:
    mock_run.return_value = MagicMock(returncode=0)
    ctx = LocalGitContext()
    ctx.git_stash_pop(Path("/test"))


@patch("subprocess.run")
def test_local_git_context_git_stash_pop_raises_on_failure(mock_run: MagicMock) -> None:
    mock_run.return_value = MagicMock(returncode=1, stderr="error")
    ctx = LocalGitContext()
    with pytest.raises(MngrError, match="git stash pop failed"):
        ctx.git_stash_pop(Path("/test"))


@patch("subprocess.run")
def test_local_git_context_git_reset_hard_succeeds(mock_run: MagicMock) -> None:
    mock_run.return_value = MagicMock(returncode=0)
    ctx = LocalGitContext()
    ctx.git_reset_hard(Path("/test"))


@patch("subprocess.run")
def test_local_git_context_git_reset_hard_raises_on_failure(mock_run: MagicMock) -> None:
    mock_run.return_value = MagicMock(returncode=1, stderr="error")
    ctx = LocalGitContext()
    with pytest.raises(MngrError, match="git reset --hard failed"):
        ctx.git_reset_hard(Path("/test"))


@patch("imbue.mngr.api.sync.get_current_branch", return_value="main")
def test_local_git_context_get_current_branch_returns_branch_name(
    mock_branch: MagicMock,
) -> None:
    ctx = LocalGitContext()
    assert ctx.get_current_branch(Path("/test")) == "main"


@patch("imbue.mngr.api.sync.is_git_repository", return_value=True)
def test_local_git_context_is_git_repository_returns_true_for_git_repo(
    mock_is_git: MagicMock,
) -> None:
    ctx = LocalGitContext()
    assert ctx.is_git_repository(Path("/test")) is True


@patch("imbue.mngr.api.sync.is_git_repository", return_value=False)
def test_local_git_context_is_git_repository_returns_false_for_non_git_dir(
    mock_is_git: MagicMock,
) -> None:
    ctx = LocalGitContext()
    assert ctx.is_git_repository(Path("/test")) is False


# =============================================================================
# RemoteGitContext tests
# =============================================================================


def test_remote_git_context_has_uncommitted_changes_returns_true_when_changes_exist() -> None:
    mock_host = MagicMock()
    mock_host.execute_command.return_value = MagicMock(success=True, stdout="M file.txt\n")
    ctx = RemoteGitContext(host=mock_host)
    assert ctx.has_uncommitted_changes(Path("/test")) is True


def test_remote_git_context_has_uncommitted_changes_returns_false_when_clean() -> None:
    mock_host = MagicMock()
    mock_host.execute_command.return_value = MagicMock(success=True, stdout="")
    ctx = RemoteGitContext(host=mock_host)
    assert ctx.has_uncommitted_changes(Path("/test")) is False


def test_remote_git_context_has_uncommitted_changes_returns_false_on_error() -> None:
    mock_host = MagicMock()
    mock_host.execute_command.return_value = MagicMock(success=False, stdout="")
    ctx = RemoteGitContext(host=mock_host)
    assert ctx.has_uncommitted_changes(Path("/test")) is False


def test_remote_git_context_git_stash_returns_true_on_success() -> None:
    mock_host = MagicMock()
    mock_host.execute_command.return_value = MagicMock(success=True, stdout="Saved")
    ctx = RemoteGitContext(host=mock_host)
    result = ctx.git_stash(Path("/test"))
    assert result is True


def test_remote_git_context_git_stash_returns_false_when_no_changes_to_save() -> None:
    mock_host = MagicMock()
    mock_host.execute_command.return_value = MagicMock(success=True, stdout="No local changes to save")
    ctx = RemoteGitContext(host=mock_host)
    result = ctx.git_stash(Path("/test"))
    assert result is False


def test_remote_git_context_git_stash_raises_on_failure() -> None:
    mock_host = MagicMock()
    mock_host.execute_command.return_value = MagicMock(success=False, stderr="error")
    ctx = RemoteGitContext(host=mock_host)
    with pytest.raises(MngrError, match="git stash failed"):
        ctx.git_stash(Path("/test"))


def test_remote_git_context_git_stash_pop_succeeds() -> None:
    mock_host = MagicMock()
    mock_host.execute_command.return_value = MagicMock(success=True)
    ctx = RemoteGitContext(host=mock_host)
    ctx.git_stash_pop(Path("/test"))


def test_remote_git_context_git_stash_pop_raises_on_failure() -> None:
    mock_host = MagicMock()
    mock_host.execute_command.return_value = MagicMock(success=False, stderr="error")
    ctx = RemoteGitContext(host=mock_host)
    with pytest.raises(MngrError, match="git stash pop failed"):
        ctx.git_stash_pop(Path("/test"))


def test_remote_git_context_git_reset_hard_succeeds() -> None:
    mock_host = MagicMock()
    mock_host.execute_command.return_value = MagicMock(success=True)
    ctx = RemoteGitContext(host=mock_host)
    ctx.git_reset_hard(Path("/test"))


def test_remote_git_context_git_reset_hard_raises_on_failure() -> None:
    mock_host = MagicMock()
    mock_host.execute_command.return_value = MagicMock(success=False, stderr="error")
    ctx = RemoteGitContext(host=mock_host)
    with pytest.raises(MngrError, match="git reset --hard failed"):
        ctx.git_reset_hard(Path("/test"))


def test_remote_git_context_get_current_branch_returns_branch_name() -> None:
    mock_host = MagicMock()
    mock_host.execute_command.return_value = MagicMock(success=True, stdout="main\n")
    ctx = RemoteGitContext(host=mock_host)
    assert ctx.get_current_branch(Path("/test")) == "main"


def test_remote_git_context_get_current_branch_raises_on_failure() -> None:
    mock_host = MagicMock()
    mock_host.execute_command.return_value = MagicMock(success=False, stderr="error")
    ctx = RemoteGitContext(host=mock_host)
    with pytest.raises(MngrError, match="Failed to get current branch"):
        ctx.get_current_branch(Path("/test"))


def test_remote_git_context_is_git_repository_returns_true_for_git_repo() -> None:
    mock_host = MagicMock()
    mock_host.execute_command.return_value = MagicMock(success=True)
    ctx = RemoteGitContext(host=mock_host)
    assert ctx.is_git_repository(Path("/test")) is True


def test_remote_git_context_is_git_repository_returns_false_for_non_git_dir() -> None:
    mock_host = MagicMock()
    mock_host.execute_command.return_value = MagicMock(success=False)
    ctx = RemoteGitContext(host=mock_host)
    assert ctx.is_git_repository(Path("/test")) is False


# =============================================================================
# handle_uncommitted_changes tests
# =============================================================================


def test_handle_uncommitted_changes_returns_false_when_no_uncommitted_changes() -> None:
    mock_ctx = MagicMock()
    mock_ctx.has_uncommitted_changes.return_value = False

    result = handle_uncommitted_changes(mock_ctx, Path("/test"), UncommittedChangesMode.FAIL)
    assert result is False


def test_handle_uncommitted_changes_raises_error_in_fail_mode() -> None:
    mock_ctx = MagicMock()
    mock_ctx.has_uncommitted_changes.return_value = True

    with pytest.raises(UncommittedChangesError) as exc_info:
        handle_uncommitted_changes(mock_ctx, Path("/test"), UncommittedChangesMode.FAIL)
    assert exc_info.value.destination == Path("/test")


def test_handle_uncommitted_changes_stashes_and_returns_true_in_stash_mode() -> None:
    mock_ctx = MagicMock()
    mock_ctx.has_uncommitted_changes.return_value = True
    mock_ctx.git_stash.return_value = True

    result = handle_uncommitted_changes(mock_ctx, Path("/test"), UncommittedChangesMode.STASH)
    assert result is True
    mock_ctx.git_stash.assert_called_once_with(Path("/test"))


def test_handle_uncommitted_changes_stashes_and_returns_true_in_merge_mode() -> None:
    mock_ctx = MagicMock()
    mock_ctx.has_uncommitted_changes.return_value = True
    mock_ctx.git_stash.return_value = True

    result = handle_uncommitted_changes(mock_ctx, Path("/test"), UncommittedChangesMode.MERGE)
    assert result is True
    mock_ctx.git_stash.assert_called_once_with(Path("/test"))


def test_handle_uncommitted_changes_resets_hard_in_clobber_mode() -> None:
    mock_ctx = MagicMock()
    mock_ctx.has_uncommitted_changes.return_value = True

    result = handle_uncommitted_changes(mock_ctx, Path("/test"), UncommittedChangesMode.CLOBBER)
    assert result is False
    mock_ctx.git_reset_hard.assert_called_once_with(Path("/test"))
