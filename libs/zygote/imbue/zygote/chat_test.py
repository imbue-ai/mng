import asyncio
from datetime import datetime
from datetime import timezone

import pytest

from imbue.zygote.chat import _thread_to_api_messages
from imbue.zygote.chat import generate_chat_response
from imbue.zygote.conftest import FakeAsyncAnthropic
from imbue.zygote.conftest import FakeMessage
from imbue.zygote.conftest import make_text_response
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


def test_thread_to_api_messages_empty_thread() -> None:
    thread = Thread(id=ThreadId())
    messages = _thread_to_api_messages(thread)
    assert messages == []


def test_thread_to_api_messages_user_message() -> None:
    thread = Thread(
        id=ThreadId(),
        messages=(_make_message(MessageRole.USER, "hello"),),
    )
    messages = _thread_to_api_messages(thread)
    assert len(messages) == 1
    assert messages[0]["role"] == "user"
    assert messages[0]["content"] == "hello"


def test_thread_to_api_messages_conversation() -> None:
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


def test_generate_chat_response_basic() -> None:
    client = FakeAsyncAnthropic([make_text_response("Hello there!")])

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
            client=client,  # type: ignore[arg-type]
            model=ModelName("claude-sonnet-4-5-20250514"),
        )
    )

    assert response == "Hello there!"


def test_generate_chat_response_includes_system_prompt() -> None:
    client = FakeAsyncAnthropic([make_text_response("response")])

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
            client=client,  # type: ignore[arg-type]
            model=ModelName("claude-sonnet-4-5-20250514"),
        )
    )

    call_kwargs = client.messages.last_call_kwargs
    assert "Base prompt." in call_kwargs["system"]
    assert "Chat prompt." in call_kwargs["system"]
    assert "Working on task X." in call_kwargs["system"]


def test_generate_chat_response_empty_thread_raises() -> None:
    client = FakeAsyncAnthropic()
    thread = Thread(id=ThreadId())

    with pytest.raises(ChatResponseError, match="empty thread"):
        asyncio.run(
            generate_chat_response(
                thread=thread,
                inner_dialog_summary="",
                base_system_prompt="prompt",
                chat_system_prompt="prompt",
                client=client,  # type: ignore[arg-type]
                model=ModelName("claude-sonnet-4-5-20250514"),
            )
        )


def test_generate_chat_response_last_message_must_be_user() -> None:
    client = FakeAsyncAnthropic()
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
                client=client,  # type: ignore[arg-type]
                model=ModelName("claude-sonnet-4-5-20250514"),
            )
        )


def test_generate_chat_response_no_text_content_raises() -> None:
    """Test that a response with no text blocks raises ChatResponseError."""

    class NoTextBlock:
        """A content block with no text attribute."""

        type = "image"

    client = FakeAsyncAnthropic([FakeMessage([NoTextBlock()])])

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
                client=client,  # type: ignore[arg-type]
                model=ModelName("claude-sonnet-4-5-20250514"),
            )
        )
