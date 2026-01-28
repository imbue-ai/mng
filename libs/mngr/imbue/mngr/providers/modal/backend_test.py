"""Tests for the Modal provider backend snapshot function utilities."""

from imbue.mngr.providers.modal.backend import _snapshot_function_url_cache
from imbue.mngr.providers.modal.backend import get_snapshot_function_url
from imbue.mngr.providers.modal.backend import reset_snapshot_function_url_cache


def test_get_snapshot_function_url_returns_none_when_not_cached() -> None:
    """get_snapshot_function_url returns None when app_name not in cache."""
    reset_snapshot_function_url_cache()
    result = get_snapshot_function_url("nonexistent-app")
    assert result is None


def test_get_snapshot_function_url_returns_cached_url() -> None:
    """get_snapshot_function_url returns the cached URL."""
    reset_snapshot_function_url_cache()
    test_url = "https://test--app-func.modal.run"
    _snapshot_function_url_cache["test-app"] = test_url

    result = get_snapshot_function_url("test-app")
    assert result == test_url


def test_reset_snapshot_function_url_cache_clears_all_entries() -> None:
    """reset_snapshot_function_url_cache clears all cached URLs."""
    _snapshot_function_url_cache["app1"] = "https://url1.modal.run"
    _snapshot_function_url_cache["app2"] = "https://url2.modal.run"

    reset_snapshot_function_url_cache()

    assert len(_snapshot_function_url_cache) == 0
    assert get_snapshot_function_url("app1") is None
    assert get_snapshot_function_url("app2") is None
