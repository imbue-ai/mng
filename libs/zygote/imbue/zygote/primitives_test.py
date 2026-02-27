import pytest

from imbue.imbue_common.ids import InvalidRandomIdError
from imbue.zygote.primitives import MemoryKey
from imbue.zygote.primitives import MessageId
from imbue.zygote.primitives import MessageRole
from imbue.zygote.primitives import ModelName
from imbue.zygote.primitives import NotificationId
from imbue.zygote.primitives import NotificationSource
from imbue.zygote.primitives import ThreadId


def test_thread_id_generate() -> None:
    thread_id = ThreadId()
    assert thread_id.startswith("thread-")


def test_thread_id_validate_valid() -> None:
    thread_id = ThreadId()
    ThreadId(str(thread_id))


def test_thread_id_validate_invalid_prefix() -> None:
    with pytest.raises(InvalidRandomIdError):
        ThreadId("bad-prefix-" + "a" * 32)


def test_message_id_generate() -> None:
    msg_id = MessageId()
    assert msg_id.startswith("msg-")


def test_notification_id_generate() -> None:
    notif_id = NotificationId()
    assert notif_id.startswith("notif-")


def test_memory_key_valid() -> None:
    key = MemoryKey("my_key")
    assert str(key) == "my_key"


def test_memory_key_empty_raises() -> None:
    with pytest.raises(ValueError):
        MemoryKey("")


def test_model_name_valid() -> None:
    name = ModelName("claude-sonnet-4-5-20250514")
    assert str(name) == "claude-sonnet-4-5-20250514"


def test_model_name_empty_raises() -> None:
    with pytest.raises(ValueError):
        ModelName("")


def test_message_role_values() -> None:
    assert MessageRole.USER.value == "USER"
    assert MessageRole.ASSISTANT.value == "ASSISTANT"


def test_notification_source_values() -> None:
    assert NotificationSource.USER_MESSAGE.value == "USER_MESSAGE"
    assert NotificationSource.SUB_AGENT_COMPLETED.value == "SUB_AGENT_COMPLETED"
    assert NotificationSource.SYSTEM.value == "SYSTEM"
