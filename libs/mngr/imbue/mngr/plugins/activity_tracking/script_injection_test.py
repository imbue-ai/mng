"""Unit tests for activity tracking script injection."""

from imbue.mngr.plugins.activity_tracking.script_injection import generate_activity_tracking_script
from imbue.mngr.plugins.activity_tracking.script_injection import generate_nginx_sub_filter_config


def test_generate_activity_tracking_script_contains_events() -> None:
    script = generate_activity_tracking_script(
        api_base_url="http://localhost:8000",
        agent_id="test-agent-123",
        api_token="test-token",
        debounce_ms=1000,
    )
    assert "keydown" in script
    assert "mousedown" in script
    assert "touchstart" in script
    assert "test-agent-123" in script


def test_generate_activity_tracking_script_uses_debounce() -> None:
    script = generate_activity_tracking_script(
        api_base_url="http://localhost:8000",
        agent_id="test-agent",
        api_token="tok",
        debounce_ms=2000,
    )
    assert "2000" in script


def test_generate_nginx_sub_filter_config_has_directives() -> None:
    config = generate_nginx_sub_filter_config(
        api_base_url="http://localhost:8000",
        agent_id="test-agent",
        api_token="tok",
        debounce_ms=1000,
    )
    assert "sub_filter" in config
    assert "</body>" in config
    assert "sub_filter_once on" in config
