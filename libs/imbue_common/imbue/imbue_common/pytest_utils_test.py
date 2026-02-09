# FIXME: Replace usages of MagicMock, Mock, patch, etc with better testing patterns like we did in create_test.py
from typing import cast
from unittest.mock import Mock

import pytest

from imbue.imbue_common.pytest_utils import inline_snapshot_is_updating


def test_inline_snapshot_is_updating_returns_false_when_no_flags() -> None:
    mock_config = Mock()
    mock_config.option.inline_snapshot = None

    assert inline_snapshot_is_updating(cast(pytest.Config, mock_config)) is False


def test_inline_snapshot_is_updating_returns_true_when_create_flag() -> None:
    mock_config = Mock()
    mock_config.option.inline_snapshot = "create"

    assert inline_snapshot_is_updating(cast(pytest.Config, mock_config)) is True


def test_inline_snapshot_is_updating_returns_true_when_fix_flag() -> None:
    mock_config = Mock()
    mock_config.option.inline_snapshot = "fix"

    assert inline_snapshot_is_updating(cast(pytest.Config, mock_config)) is True


def test_inline_snapshot_is_updating_returns_true_when_create_and_other_flags() -> None:
    mock_config = Mock()
    mock_config.option.inline_snapshot = "report,create,update"

    assert inline_snapshot_is_updating(cast(pytest.Config, mock_config)) is True


def test_inline_snapshot_is_updating_returns_true_when_fix_and_other_flags() -> None:
    mock_config = Mock()
    mock_config.option.inline_snapshot = "report,fix,update"

    assert inline_snapshot_is_updating(cast(pytest.Config, mock_config)) is True


def test_inline_snapshot_is_updating_returns_false_when_only_other_flags() -> None:
    mock_config = Mock()
    mock_config.option.inline_snapshot = "report,update,trim"

    assert inline_snapshot_is_updating(cast(pytest.Config, mock_config)) is False


def test_inline_snapshot_is_updating_returns_false_when_disabled() -> None:
    mock_config = Mock()
    mock_config.option.inline_snapshot = "disable"

    assert inline_snapshot_is_updating(cast(pytest.Config, mock_config)) is False
