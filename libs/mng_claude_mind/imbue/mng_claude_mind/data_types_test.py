"""Unit tests for claude mind data types."""

from imbue.mng_claude_mind.data_types import ClaudeMindSettings
from imbue.mng_claude_mind.data_types import WatcherSettings


def test_claude_mind_settings_defaults() -> None:
    settings = ClaudeMindSettings()
    assert settings.agent_type is None
    assert settings.watchers == WatcherSettings()


def test_claude_mind_settings_with_agent_type() -> None:
    settings = ClaudeMindSettings.model_validate({"agent_type": "claude-mind"})
    assert settings.agent_type == "claude-mind"


def test_claude_mind_settings_re_exports_common_types() -> None:
    """Verify that common types are re-exported for backward compatibility."""
    from imbue.mng_claude_mind.data_types import ConversationId
    from imbue.mng_claude_mind.data_types import MessageEvent
    from imbue.mng_claude_mind.data_types import MindEvent
    from imbue.mng_claude_mind.data_types import SOURCE_MESSAGES

    assert ConversationId("conv-1") == "conv-1"
    assert SOURCE_MESSAGES == "messages"
    assert MessageEvent is not None
    assert MindEvent is not None
