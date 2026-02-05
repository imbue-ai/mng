"""Tests for create module helper functions."""

from unittest.mock import MagicMock

from imbue.mngr.cli.create import _parse_host_lifecycle_options
from imbue.mngr.primitives import ActivitySource
from imbue.mngr.primitives import IdleMode


def test_parse_host_lifecycle_options_all_none() -> None:
    """When all CLI options are None, result should have all None values."""
    opts = MagicMock()
    opts.idle_timeout = None
    opts.idle_mode = None
    opts.activity_sources = None

    result = _parse_host_lifecycle_options(opts)

    assert result.idle_timeout_seconds is None
    assert result.idle_mode is None
    assert result.activity_sources is None


def test_parse_host_lifecycle_options_with_idle_timeout() -> None:
    """idle_timeout should be passed through directly."""
    opts = MagicMock()
    opts.idle_timeout = 600
    opts.idle_mode = None
    opts.activity_sources = None

    result = _parse_host_lifecycle_options(opts)

    assert result.idle_timeout_seconds == 600
    assert result.idle_mode is None
    assert result.activity_sources is None


def test_parse_host_lifecycle_options_with_idle_mode_lowercase() -> None:
    """idle_mode should be parsed and uppercased to IdleMode enum."""
    opts = MagicMock()
    opts.idle_timeout = None
    opts.idle_mode = "agent"
    opts.activity_sources = None

    result = _parse_host_lifecycle_options(opts)

    assert result.idle_timeout_seconds is None
    assert result.idle_mode == IdleMode.AGENT
    assert result.activity_sources is None


def test_parse_host_lifecycle_options_with_idle_mode_uppercase() -> None:
    """idle_mode should work with uppercase input."""
    opts = MagicMock()
    opts.idle_timeout = None
    opts.idle_mode = "SSH"
    opts.activity_sources = None

    result = _parse_host_lifecycle_options(opts)

    assert result.idle_mode == IdleMode.SSH


def test_parse_host_lifecycle_options_with_activity_sources_single() -> None:
    """activity_sources should parse a single source."""
    opts = MagicMock()
    opts.idle_timeout = None
    opts.idle_mode = None
    opts.activity_sources = "boot"

    result = _parse_host_lifecycle_options(opts)

    assert result.activity_sources == (ActivitySource.BOOT,)


def test_parse_host_lifecycle_options_with_activity_sources_multiple() -> None:
    """activity_sources should parse comma-separated sources."""
    opts = MagicMock()
    opts.idle_timeout = None
    opts.idle_mode = None
    opts.activity_sources = "boot,ssh,agent"

    result = _parse_host_lifecycle_options(opts)

    assert result.activity_sources == (ActivitySource.BOOT, ActivitySource.SSH, ActivitySource.AGENT)


def test_parse_host_lifecycle_options_with_activity_sources_whitespace() -> None:
    """activity_sources should handle whitespace around commas."""
    opts = MagicMock()
    opts.idle_timeout = None
    opts.idle_mode = None
    opts.activity_sources = "boot , ssh , agent"

    result = _parse_host_lifecycle_options(opts)

    assert result.activity_sources == (ActivitySource.BOOT, ActivitySource.SSH, ActivitySource.AGENT)


def test_parse_host_lifecycle_options_all_provided() -> None:
    """All options should be correctly parsed when all are provided."""
    opts = MagicMock()
    opts.idle_timeout = 1800
    opts.idle_mode = "disabled"
    opts.activity_sources = "create,process"

    result = _parse_host_lifecycle_options(opts)

    assert result.idle_timeout_seconds == 1800
    assert result.idle_mode == IdleMode.DISABLED
    assert result.activity_sources == (ActivitySource.CREATE, ActivitySource.PROCESS)
