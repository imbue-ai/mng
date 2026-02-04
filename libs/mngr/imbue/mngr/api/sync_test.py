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


class TestSyncMode:
    """Tests for the SyncMode enum."""

    def test_sync_mode_push_value(self) -> None:
        assert SyncMode.PUSH.value == "PUSH"

    def test_sync_mode_pull_value(self) -> None:
        assert SyncMode.PULL.value == "PULL"


class TestSyncFilesResult:
    """Tests for the SyncFilesResult model."""

    def test_create_sync_files_result(self) -> None:
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

    def test_sync_files_result_dry_run(self) -> None:
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

    def test_sync_files_result_serialization(self) -> None:
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


class TestSyncGitResult:
    """Tests for the SyncGitResult model."""

    def test_create_sync_git_result(self) -> None:
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

    def test_sync_git_result_dry_run(self) -> None:
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


class TestUncommittedChangesError:
    """Tests for the UncommittedChangesError class."""

    def test_error_message(self) -> None:
        error = UncommittedChangesError(Path("/some/path"))
        assert "Uncommitted changes" in str(error)
        assert "/some/path" in str(error)

    def test_error_has_user_help_text(self) -> None:
        error = UncommittedChangesError(Path("/some/path"))
        assert "stash" in error.user_help_text.lower()
        assert "clobber" in error.user_help_text.lower()

    def test_error_stores_destination(self) -> None:
        error = UncommittedChangesError(Path("/test/path"))
        assert error.destination == Path("/test/path")


class TestNotAGitRepositoryError:
    """Tests for the NotAGitRepositoryError class."""

    def test_error_message(self) -> None:
        error = NotAGitRepositoryError(Path("/not/a/repo"))
        assert "Not a git repository" in str(error)
        assert "/not/a/repo" in str(error)

    def test_error_has_user_help_text(self) -> None:
        error = NotAGitRepositoryError(Path("/some/path"))
        assert "sync-mode=files" in error.user_help_text

    def test_error_stores_path(self) -> None:
        error = NotAGitRepositoryError(Path("/test/path"))
        assert error.path == Path("/test/path")


class TestGitSyncError:
    """Tests for the GitSyncError class."""

    def test_error_message(self) -> None:
        error = GitSyncError("something went wrong")
        assert "Git sync failed" in str(error)
        assert "something went wrong" in str(error)

    def test_error_has_user_help_text(self) -> None:
        error = GitSyncError("test")
        assert error.user_help_text is not None


class TestLocalGitContext:
    """Tests for the LocalGitContext class."""

    @patch("subprocess.run")
    def test_has_uncommitted_changes_true(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(returncode=0, stdout="M file.txt\n")
        ctx = LocalGitContext()
        assert ctx.has_uncommitted_changes(Path("/test")) is True

    @patch("subprocess.run")
    def test_has_uncommitted_changes_false(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(returncode=0, stdout="")
        ctx = LocalGitContext()
        assert ctx.has_uncommitted_changes(Path("/test")) is False

    @patch("subprocess.run")
    def test_has_uncommitted_changes_error_returns_false(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(returncode=1, stdout="")
        ctx = LocalGitContext()
        assert ctx.has_uncommitted_changes(Path("/test")) is False

    @patch("subprocess.run")
    def test_git_stash_success(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(returncode=0, stdout="Saved working directory")
        ctx = LocalGitContext()
        result = ctx.git_stash(Path("/test"))
        assert result is True

    @patch("subprocess.run")
    def test_git_stash_no_changes(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(returncode=0, stdout="No local changes to save")
        ctx = LocalGitContext()
        result = ctx.git_stash(Path("/test"))
        assert result is False

    @patch("subprocess.run")
    def test_git_stash_failure(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(returncode=1, stderr="error")
        ctx = LocalGitContext()
        with pytest.raises(MngrError, match="git stash failed"):
            ctx.git_stash(Path("/test"))

    @patch("subprocess.run")
    def test_git_stash_pop_success(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(returncode=0)
        ctx = LocalGitContext()
        ctx.git_stash_pop(Path("/test"))

    @patch("subprocess.run")
    def test_git_stash_pop_failure(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(returncode=1, stderr="error")
        ctx = LocalGitContext()
        with pytest.raises(MngrError, match="git stash pop failed"):
            ctx.git_stash_pop(Path("/test"))

    @patch("subprocess.run")
    def test_git_reset_hard_success(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(returncode=0)
        ctx = LocalGitContext()
        ctx.git_reset_hard(Path("/test"))

    @patch("subprocess.run")
    def test_git_reset_hard_failure(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(returncode=1, stderr="error")
        ctx = LocalGitContext()
        with pytest.raises(MngrError, match="git reset --hard failed"):
            ctx.git_reset_hard(Path("/test"))

    @patch("imbue.mngr.api.sync.get_current_branch", return_value="main")
    def test_get_current_branch(self, mock_branch: MagicMock) -> None:
        ctx = LocalGitContext()
        assert ctx.get_current_branch(Path("/test")) == "main"

    @patch("imbue.mngr.api.sync.is_git_repository", return_value=True)
    def test_is_git_repository_true(self, mock_is_git: MagicMock) -> None:
        ctx = LocalGitContext()
        assert ctx.is_git_repository(Path("/test")) is True

    @patch("imbue.mngr.api.sync.is_git_repository", return_value=False)
    def test_is_git_repository_false(self, mock_is_git: MagicMock) -> None:
        ctx = LocalGitContext()
        assert ctx.is_git_repository(Path("/test")) is False


class TestRemoteGitContext:
    """Tests for the RemoteGitContext class."""

    def test_has_uncommitted_changes_true(self) -> None:
        mock_host = MagicMock()
        mock_host.execute_command.return_value = MagicMock(success=True, stdout="M file.txt\n")
        ctx = RemoteGitContext(host=mock_host)
        assert ctx.has_uncommitted_changes(Path("/test")) is True

    def test_has_uncommitted_changes_false(self) -> None:
        mock_host = MagicMock()
        mock_host.execute_command.return_value = MagicMock(success=True, stdout="")
        ctx = RemoteGitContext(host=mock_host)
        assert ctx.has_uncommitted_changes(Path("/test")) is False

    def test_has_uncommitted_changes_error_returns_false(self) -> None:
        mock_host = MagicMock()
        mock_host.execute_command.return_value = MagicMock(success=False, stdout="")
        ctx = RemoteGitContext(host=mock_host)
        assert ctx.has_uncommitted_changes(Path("/test")) is False

    def test_git_stash_success(self) -> None:
        mock_host = MagicMock()
        mock_host.execute_command.return_value = MagicMock(success=True, stdout="Saved")
        ctx = RemoteGitContext(host=mock_host)
        result = ctx.git_stash(Path("/test"))
        assert result is True

    def test_git_stash_no_changes(self) -> None:
        mock_host = MagicMock()
        mock_host.execute_command.return_value = MagicMock(success=True, stdout="No local changes to save")
        ctx = RemoteGitContext(host=mock_host)
        result = ctx.git_stash(Path("/test"))
        assert result is False

    def test_git_stash_failure(self) -> None:
        mock_host = MagicMock()
        mock_host.execute_command.return_value = MagicMock(success=False, stderr="error")
        ctx = RemoteGitContext(host=mock_host)
        with pytest.raises(MngrError, match="git stash failed"):
            ctx.git_stash(Path("/test"))

    def test_git_stash_pop_success(self) -> None:
        mock_host = MagicMock()
        mock_host.execute_command.return_value = MagicMock(success=True)
        ctx = RemoteGitContext(host=mock_host)
        ctx.git_stash_pop(Path("/test"))

    def test_git_stash_pop_failure(self) -> None:
        mock_host = MagicMock()
        mock_host.execute_command.return_value = MagicMock(success=False, stderr="error")
        ctx = RemoteGitContext(host=mock_host)
        with pytest.raises(MngrError, match="git stash pop failed"):
            ctx.git_stash_pop(Path("/test"))

    def test_git_reset_hard_success(self) -> None:
        mock_host = MagicMock()
        mock_host.execute_command.return_value = MagicMock(success=True)
        ctx = RemoteGitContext(host=mock_host)
        ctx.git_reset_hard(Path("/test"))

    def test_git_reset_hard_failure(self) -> None:
        mock_host = MagicMock()
        mock_host.execute_command.return_value = MagicMock(success=False, stderr="error")
        ctx = RemoteGitContext(host=mock_host)
        with pytest.raises(MngrError, match="git reset --hard failed"):
            ctx.git_reset_hard(Path("/test"))

    def test_get_current_branch_success(self) -> None:
        mock_host = MagicMock()
        mock_host.execute_command.return_value = MagicMock(success=True, stdout="main\n")
        ctx = RemoteGitContext(host=mock_host)
        assert ctx.get_current_branch(Path("/test")) == "main"

    def test_get_current_branch_failure(self) -> None:
        mock_host = MagicMock()
        mock_host.execute_command.return_value = MagicMock(success=False, stderr="error")
        ctx = RemoteGitContext(host=mock_host)
        with pytest.raises(MngrError, match="Failed to get current branch"):
            ctx.get_current_branch(Path("/test"))

    def test_is_git_repository_true(self) -> None:
        mock_host = MagicMock()
        mock_host.execute_command.return_value = MagicMock(success=True)
        ctx = RemoteGitContext(host=mock_host)
        assert ctx.is_git_repository(Path("/test")) is True

    def test_is_git_repository_false(self) -> None:
        mock_host = MagicMock()
        mock_host.execute_command.return_value = MagicMock(success=False)
        ctx = RemoteGitContext(host=mock_host)
        assert ctx.is_git_repository(Path("/test")) is False


class TestHandleUncommittedChanges:
    """Tests for the handle_uncommitted_changes function."""

    def test_no_uncommitted_changes_returns_false(self) -> None:
        mock_ctx = MagicMock()
        mock_ctx.has_uncommitted_changes.return_value = False

        result = handle_uncommitted_changes(mock_ctx, Path("/test"), UncommittedChangesMode.FAIL)
        assert result is False

    def test_fail_mode_raises_error(self) -> None:
        mock_ctx = MagicMock()
        mock_ctx.has_uncommitted_changes.return_value = True

        with pytest.raises(UncommittedChangesError) as exc_info:
            handle_uncommitted_changes(mock_ctx, Path("/test"), UncommittedChangesMode.FAIL)
        assert exc_info.value.destination == Path("/test")

    def test_stash_mode_stashes_and_returns_true(self) -> None:
        mock_ctx = MagicMock()
        mock_ctx.has_uncommitted_changes.return_value = True
        mock_ctx.git_stash.return_value = True

        result = handle_uncommitted_changes(mock_ctx, Path("/test"), UncommittedChangesMode.STASH)
        assert result is True
        mock_ctx.git_stash.assert_called_once_with(Path("/test"))

    def test_merge_mode_stashes_and_returns_true(self) -> None:
        mock_ctx = MagicMock()
        mock_ctx.has_uncommitted_changes.return_value = True
        mock_ctx.git_stash.return_value = True

        result = handle_uncommitted_changes(mock_ctx, Path("/test"), UncommittedChangesMode.MERGE)
        assert result is True
        mock_ctx.git_stash.assert_called_once_with(Path("/test"))

    def test_clobber_mode_resets_hard(self) -> None:
        mock_ctx = MagicMock()
        mock_ctx.has_uncommitted_changes.return_value = True

        result = handle_uncommitted_changes(mock_ctx, Path("/test"), UncommittedChangesMode.CLOBBER)
        assert result is False
        mock_ctx.git_reset_hard.assert_called_once_with(Path("/test"))
