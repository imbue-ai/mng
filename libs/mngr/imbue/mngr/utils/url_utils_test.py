"""Unit tests for url_utils."""

from imbue.mngr.utils.url_utils import compute_default_url


def test_compute_default_url_returns_default_key_when_present() -> None:
    urls = {"default": "https://example.com/default", "terminal": "https://example.com/ttyd"}
    assert compute_default_url(urls) == "https://example.com/default"


def test_compute_default_url_returns_only_entry_when_single_non_default() -> None:
    urls = {"terminal": "https://example.com/ttyd"}
    assert compute_default_url(urls) == "https://example.com/ttyd"


def test_compute_default_url_returns_none_for_empty_dict() -> None:
    assert compute_default_url({}) is None


def test_compute_default_url_returns_none_for_multiple_non_default_entries() -> None:
    urls = {"terminal": "https://example.com/ttyd", "chat": "https://example.com/chat"}
    assert compute_default_url(urls) is None


def test_compute_default_url_prefers_default_over_single_entry() -> None:
    urls = {"default": "https://example.com/default"}
    assert compute_default_url(urls) == "https://example.com/default"
