"""Tests for Modal deploy utilities."""

from unittest.mock import patch

from imbue.mngr.providers.modal.deploy_utils import deploy_snapshot_function


def test_deploy_snapshot_function_parses_url_on_same_line() -> None:
    """URL on the same line as snapshot_and_shutdown should be parsed."""
    mock_output = """View Deployment: https://modal.com/apps/some-app
Created web function snapshot_and_shutdown => https://test--app-func.modal.run
Deployment complete!
"""
    with patch("imbue.mngr.providers.modal.deploy_utils.subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = mock_output

        url = deploy_snapshot_function("test-app", "test-env")

        assert url == "https://test--app-func.modal.run"


def test_deploy_snapshot_function_parses_url_on_next_line() -> None:
    """URL on the next line after snapshot_and_shutdown should be parsed."""
    mock_output = """View Deployment: https://modal.com/apps/some-app
Created web function snapshot_and_shutdown
=> https://test--app-func.modal.run
Deployment complete!
"""
    with patch("imbue.mngr.providers.modal.deploy_utils.subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = mock_output

        url = deploy_snapshot_function("test-app", "test-env")

        assert url == "https://test--app-func.modal.run"


def test_deploy_snapshot_function_returns_none_on_failure() -> None:
    """Should return None when deployment fails."""
    with patch("imbue.mngr.providers.modal.deploy_utils.subprocess.run") as mock_run:
        mock_run.return_value.returncode = 1
        mock_run.return_value.stderr = "Error deploying"

        url = deploy_snapshot_function("test-app", "test-env")

        assert url is None


def test_deploy_snapshot_function_returns_none_when_url_not_found() -> None:
    """Should return None when URL is not found in output."""
    mock_output = """Deployment complete but no URL in output"""
    with patch("imbue.mngr.providers.modal.deploy_utils.subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = mock_output

        url = deploy_snapshot_function("test-app", "test-env")

        assert url is None


def test_deploy_snapshot_function_strips_trailing_parenthesis() -> None:
    """URL with trailing parenthesis should have it stripped."""
    mock_output = """Created web function snapshot_and_shutdown => https://test--app-func.modal.run)"""
    with patch("imbue.mngr.providers.modal.deploy_utils.subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = mock_output

        url = deploy_snapshot_function("test-app", "test-env")

        assert url == "https://test--app-func.modal.run"
