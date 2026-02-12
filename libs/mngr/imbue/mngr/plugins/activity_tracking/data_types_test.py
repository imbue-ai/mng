"""Unit tests for activity tracking data types."""

from imbue.mngr.plugins.activity_tracking.data_types import ActivityTrackingConfig
from imbue.mngr.plugins.activity_tracking.data_types import DEFAULT_DEBOUNCE_MS


def test_activity_tracking_config_has_defaults() -> None:
    config = ActivityTrackingConfig()
    assert config.debounce_ms == DEFAULT_DEBOUNCE_MS
    assert config.enabled is True
