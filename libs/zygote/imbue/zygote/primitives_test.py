import pytest

from imbue.imbue_common.ids import InvalidRandomIdError
from imbue.zygote.primitives import MemoryKey
from imbue.zygote.primitives import MessageId
from imbue.zygote.primitives import MessageRole
from imbue.zygote.primitives import ModelName
from imbue.zygote.primitives import NotificationId
from imbue.zygote.primitives import NotificationSource
from imbue.zygote.primitives import ThreadId


class TestThreadId:
    def test_generate(self) -> None:
        thread_id = ThreadId()
        assert thread_id.startswith("thread-")

    def test_validate_valid(self) -> None:
        thread_id = ThreadId()
        ThreadId(str(thread_id))

    def test_validate_invalid_prefix(self) -> None:
        with pytest.raises(InvalidRandomIdError):
            ThreadId("bad-prefix-" + "a" * 32)


class TestMessageId:
    def test_generate(self) -> None:
        msg_id = MessageId()
        assert msg_id.startswith("msg-")


class TestNotificationId:
    def test_generate(self) -> None:
        notif_id = NotificationId()
        assert notif_id.startswith("notif-")


class TestMemoryKey:
    def test_valid(self) -> None:
        key = MemoryKey("my_key")
        assert str(key) == "my_key"

    def test_empty_raises(self) -> None:
        with pytest.raises(ValueError):
            MemoryKey("")


class TestModelName:
    def test_valid(self) -> None:
        name = ModelName("claude-sonnet-4-5-20250514")
        assert str(name) == "claude-sonnet-4-5-20250514"

    def test_empty_raises(self) -> None:
        with pytest.raises(ValueError):
            ModelName("")


class TestMessageRole:
    def test_values(self) -> None:
        assert MessageRole.USER.value == "USER"
        assert MessageRole.ASSISTANT.value == "ASSISTANT"


class TestNotificationSource:
    def test_values(self) -> None:
        assert NotificationSource.USER_MESSAGE.value == "USER_MESSAGE"
        assert NotificationSource.SUB_AGENT_COMPLETED.value == "SUB_AGENT_COMPLETED"
        assert NotificationSource.SYSTEM.value == "SYSTEM"
