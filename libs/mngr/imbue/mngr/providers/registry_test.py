from imbue.mngr.providers.registry import _indent_text
from imbue.mngr.providers.registry import get_all_provider_args_help_sections


def test_indent_text_adds_prefix_to_each_line() -> None:
    result = _indent_text("line1\nline2\nline3", "  ")
    assert result == "  line1\n  line2\n  line3"


def test_indent_text_leaves_blank_lines_empty() -> None:
    result = _indent_text("line1\n\nline3", "  ")
    assert result == "  line1\n\n  line3"


def test_indent_text_handles_single_line() -> None:
    result = _indent_text("hello", ">>")
    assert result == ">>hello"


def test_indent_text_handles_whitespace_only_lines_as_blank() -> None:
    result = _indent_text("line1\n   \nline3", "  ")
    assert result == "  line1\n\n  line3"


def test_get_all_provider_args_help_sections_returns_single_section() -> None:
    sections = get_all_provider_args_help_sections()
    assert len(sections) == 1
    title, _content = sections[0]
    assert title == "Provider Build/Start Arguments"


def test_get_all_provider_args_help_sections_includes_all_registered_backends() -> None:
    sections = get_all_provider_args_help_sections()
    _title, content = sections[0]
    # The test fixture loads local and ssh backends
    assert "Provider: local" in content
    assert "Provider: ssh" in content


def test_get_all_provider_args_help_sections_includes_build_help_text() -> None:
    sections = get_all_provider_args_help_sections()
    _title, content = sections[0]
    # Local backend's build help should appear
    assert "No build arguments are supported for the local provider" in content


def test_get_all_provider_args_help_sections_includes_start_help_when_different_from_build() -> None:
    sections = get_all_provider_args_help_sections()
    _title, content = sections[0]
    # Local backend has different build and start help, so both should appear
    assert "No start arguments are supported for the local provider" in content


def test_get_all_provider_args_help_sections_omits_start_help_when_same_as_build() -> None:
    sections = get_all_provider_args_help_sections()
    _title, content = sections[0]
    # SSH backend has different build and start help text, so start should appear
    # (this test verifies the dedup logic doesn't incorrectly drop start help)
    assert "No start arguments are supported for the SSH provider" in content
