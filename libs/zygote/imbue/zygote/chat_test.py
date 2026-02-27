import asyncio
from datetime import datetime
from datetime import timezone
from unittest.mock import AsyncMock
from unittest.mock import MagicMock

import anthropic
import pytest

from imbue.zygote.chat import _thread_to_api_messages
from imbue.zygote.chat import generate_chat_response
from imbue.zygote.data_types import Thread
from imbue.zygote.data_types import ThreadMessage
from imbue.zygote.errors import ChatResponseError
from imbue.zygote.primitives import MessageId
from imbue.zygote.primitives import MessageRole
from imbue.zygote.primitives import ModelName
from imbue.zygote.primitives import ThreadId


def _make_message(role: MessageRole, content: str) -> ThreadMessage:
    return ThreadMessage(
        id=MessageId(),
        role=role,
        content=content,
        timestamp=datetime.now(timezone.utc),
    )


class TestThreadToApiMessages:
    def test_empty_thread(self) -> None:
        thread = Thread(id=ThreadId())
        messages = _thread_to_api_messages(thread)
        assert messages == []

    def test_user_message(self) -> None:
        thread = Thread(
            id=ThreadId(),
            messages=(_make_message(MessageRole.USER, "hello"),),
        )
        messages = _thread_to_api_messages(thread)
        assert len(messages) == 1
        assert messages[0]["role"] == "user"
        assert messages[0]["content"] == "hello"

    def test_conversation(self) -> None:
        thread = Thread(
            id=ThreadId(),
            messages=(
                _make_message(MessageRole.USER, "hi"),
                _make_message(MessageRole.ASSISTANT, "hello!"),
                _make_message(MessageRole.USER, "how are you?"),
            ),
        )
        messages = _thread_to_api_messages(thread)
        assert len(messages) == 3
        assert messages[0]["role"] == "user"
        assert messages[1]["role"] == "assistant"
        assert messages[2]["role"] == "user"


class TestGenerateChatResponse:
    def test_basic_response(self) -> None:
        client = AsyncMock()
        text_block = MagicMock()
        text_block.text = "Hello there!"
        client.messages.create = AsyncMock(return_value=MagicMock(content=[text_block]))

        thread = Thread(
            id=ThreadId(),
            messages=(_make_message(MessageRole.USER, "hi"),),
        )

        response = asyncio.run(
            generate_chat_response(
                thread=thread,
                inner_dialog_summary="Agent is idle.",
                base_system_prompt="You are helpful.",
                chat_system_prompt="Be concise.",
                client=client,
                model=ModelName("claude-sonnet-4-5-20250514"),
            )
        )

        assert response == "Hello there!"
        client.messages.create.assert_called_once()

    def test_includes_system_prompt(self) -> None:
        client = AsyncMock()
        text_block = MagicMock()
        text_block.text = "response"
        client.messages.create = AsyncMock(return_value=MagicMock(content=[text_block]))

        thread = Thread(
            id=ThreadId(),
            messages=(_make_message(MessageRole.USER, "hi"),),
        )

        asyncio.run(
            generate_chat_response(
                thread=thread,
                inner_dialog_summary="Working on task X.",
                base_system_prompt="Base prompt.",
                chat_system_prompt="Chat prompt.",
                client=client,
                model=ModelName("claude-sonnet-4-5-20250514"),
            )
        )

        call_kwargs = client.messages.create.call_args.kwargs
        assert "Base prompt." in call_kwargs["system"]
        assert "Chat prompt." in call_kwargs["system"]
        assert "Working on task X." in call_kwargs["system"]

    def test_empty_thread_raises(self) -> None:
        client = AsyncMock()
        thread = Thread(id=ThreadId())

        with pytest.raises(ChatResponseError, match="empty thread"):
            asyncio.run(
                generate_chat_response(
                    thread=thread,
                    inner_dialog_summary="",
                    base_system_prompt="prompt",
                    chat_system_prompt="prompt",
                    client=client,
                    model=ModelName("claude-sonnet-4-5-20250514"),
                )
            )

    def test_last_message_must_be_user(self) -> None:
        client = AsyncMock()
        thread = Thread(
            id=ThreadId(),
            messages=(
                _make_message(MessageRole.USER, "hi"),
                _make_message(MessageRole.ASSISTANT, "hello"),
            ),
        )

        with pytest.raises(ChatResponseError, match="last message must be from the user"):
            asyncio.run(
                generate_chat_response(
                    thread=thread,
                    inner_dialog_summary="",
                    base_system_prompt="prompt",
                    chat_system_prompt="prompt",
                    client=client,
                    model=ModelName("claude-sonnet-4-5-20250514"),
                )
            )

    def test_api_error_wrapped(self) -> None:
        client = AsyncMock()
        client.messages.create = AsyncMock(side_effect=anthropic.APIConnectionError(request=MagicMock()))

        thread = Thread(
            id=ThreadId(),
            messages=(_make_message(MessageRole.USER, "hi"),),
        )

        with pytest.raises(ChatResponseError, match="API error"):
            asyncio.run(
                generate_chat_response(
                    thread=thread,
                    inner_dialog_summary="",
                    base_system_prompt="prompt",
                    chat_system_prompt="prompt",
                    client=client,
                    model=ModelName("claude-sonnet-4-5-20250514"),
                )
            )

    def test_no_text_content_raises(self) -> None:
        client = AsyncMock()
        # Response with no text blocks
        non_text_block = MagicMock(spec=[])
        client.messages.create = AsyncMock(return_value=MagicMock(content=[non_text_block]))

        thread = Thread(
            id=ThreadId(),
            messages=(_make_message(MessageRole.USER, "hi"),),
        )

        with pytest.raises(ChatResponseError, match="no text content"):
            asyncio.run(
                generate_chat_response(
                    thread=thread,
                    inner_dialog_summary="",
                    base_system_prompt="prompt",
                    chat_system_prompt="prompt",
                    client=client,
                    model=ModelName("claude-sonnet-4-5-20250514"),
                )
            )
