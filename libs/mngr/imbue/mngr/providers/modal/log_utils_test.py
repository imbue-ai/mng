from io import StringIO

from imbue.mngr.providers.modal.log_utils import _create_deduplicating_writer
from imbue.mngr.providers.modal.log_utils import _create_modal_loguru_writer
from imbue.mngr.providers.modal.log_utils import _create_multi_writer
from imbue.mngr.providers.modal.log_utils import _ModalLoguruWriter
from imbue.mngr.providers.modal.log_utils import enable_modal_output_capture


def test_deduplicating_writer_writes_unique_messages() -> None:
    """Should write unique messages to the buffer."""
    writer = _create_deduplicating_writer()
    writer.write("message 1")
    writer.write("message 2")
    writer.write("message 3")

    assert "message 1" in writer.getvalue()
    assert "message 2" in writer.getvalue()
    assert "message 3" in writer.getvalue()


def test_deduplicating_writer_deduplicates_consecutive_identical_messages() -> None:
    """Should skip consecutive duplicate messages."""
    writer = _create_deduplicating_writer()
    writer.write("same message")
    writer.write("same message")
    writer.write("same message")

    assert writer.getvalue().count("same message") == 1


def test_deduplicating_writer_allows_non_consecutive_duplicates() -> None:
    """Should allow the same message to appear non-consecutively."""
    writer = _create_deduplicating_writer()
    writer.write("message a")
    writer.write("message b")
    writer.write("message a")

    content = writer.getvalue()
    assert content.count("message a") == 2
    assert content.count("message b") == 1


def test_deduplicating_writer_skips_empty_messages() -> None:
    """Should skip empty messages."""
    writer = _create_deduplicating_writer()
    writer.write("")
    writer.write("   ")
    writer.write("\n")
    writer.write("real message")

    assert writer.getvalue() == "real message"


def test_multi_writer_writes_to_all_files() -> None:
    """Should write to all file-like objects."""
    buffer1 = StringIO()
    buffer2 = StringIO()
    multi = _create_multi_writer([buffer1, buffer2])

    multi.write("test message")

    assert buffer1.getvalue() == "test message"
    assert buffer2.getvalue() == "test message"


def test_multi_writer_is_not_a_tty() -> None:
    """Should report as not a tty to disable interactive features."""
    multi = _create_multi_writer([])
    assert multi.isatty() is False


def test_multi_writer_context_manager() -> None:
    """Should work as a context manager."""
    buffer = StringIO()
    with _create_multi_writer([buffer]) as multi:
        multi.write("inside context")

    assert buffer.getvalue() == "inside context"


def test_modal_loguru_writer_app_metadata_can_be_set() -> None:
    """Should allow setting app_id and app_name."""
    writer = _create_modal_loguru_writer()
    writer.app_id = "test-app-id"
    writer.app_name = "test-app-name"

    assert writer.app_id == "test-app-id"
    assert writer.app_name == "test-app-name"


def test_modal_loguru_writer_initial_metadata_is_none() -> None:
    """Should have None for app metadata initially."""
    writer = _create_modal_loguru_writer()
    assert writer.app_id is None
    assert writer.app_name is None


def test_modal_loguru_writer_is_writable() -> None:
    """Should report as writable."""
    writer = _create_modal_loguru_writer()
    assert writer.writable() is True
    assert writer.readable() is False
    assert writer.seekable() is False


def test_modal_loguru_writer_deduplicates_messages() -> None:
    """Should deduplicate consecutive messages."""
    writer = _create_modal_loguru_writer()

    writer.write("same message")
    result1 = writer.write("same message")

    assert result1 == len("same message")


def test_enable_modal_output_capture_returns_buffer_and_writer() -> None:
    """Should return a StringIO buffer and optional loguru writer."""
    with enable_modal_output_capture(is_logging_to_loguru=True) as (buffer, writer):
        assert isinstance(buffer, StringIO)
        assert writer is not None
        assert isinstance(writer, _ModalLoguruWriter)


def test_enable_modal_output_capture_returns_none_writer_when_disabled() -> None:
    """Should return None for writer when logging to loguru is disabled."""
    with enable_modal_output_capture(is_logging_to_loguru=False) as (buffer, writer):
        assert isinstance(buffer, StringIO)
        assert writer is None


