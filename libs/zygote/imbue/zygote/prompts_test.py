from imbue.zygote.prompts import build_chat_full_prompt
from imbue.zygote.prompts import build_compaction_prompt
from imbue.zygote.prompts import build_inner_dialog_full_prompt


class TestBuildInnerDialogFullPrompt:
    def test_combines_base_and_inner(self) -> None:
        result = build_inner_dialog_full_prompt(
            base_prompt="You are a helpful agent.",
            inner_dialog_prompt="Think step by step.",
        )
        assert "You are a helpful agent." in result
        assert "Think step by step." in result
        assert "Inner Dialog Instructions" in result

    def test_preserves_ordering(self) -> None:
        result = build_inner_dialog_full_prompt(
            base_prompt="BASE",
            inner_dialog_prompt="INNER",
        )
        assert result.index("BASE") < result.index("INNER")


class TestBuildChatFullPrompt:
    def test_combines_base_and_chat(self) -> None:
        result = build_chat_full_prompt(
            base_prompt="You are a helpful agent.",
            chat_prompt="Be concise in replies.",
            inner_dialog_summary="",
        )
        assert "You are a helpful agent." in result
        assert "Be concise in replies." in result
        assert "Chat Response Instructions" in result

    def test_includes_inner_dialog_summary(self) -> None:
        result = build_chat_full_prompt(
            base_prompt="BASE",
            chat_prompt="CHAT",
            inner_dialog_summary="Working on task X.",
        )
        assert "Working on task X." in result
        assert "Current Agent State" in result

    def test_omits_state_section_when_summary_empty(self) -> None:
        result = build_chat_full_prompt(
            base_prompt="BASE",
            chat_prompt="CHAT",
            inner_dialog_summary="",
        )
        assert "Current Agent State" not in result


class TestBuildCompactionPrompt:
    def test_includes_messages(self) -> None:
        result = build_compaction_prompt("user: hello\nassistant: hi there")
        assert "user: hello" in result
        assert "Summarize" in result
