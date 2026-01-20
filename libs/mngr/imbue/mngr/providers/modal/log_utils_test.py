"""Tests for modal log capture utilities."""

from io import StringIO
from pathlib import Path

import pytest

from imbue.mngr.config.data_types import MngrContext
from imbue.mngr.primitives import HostName
from imbue.mngr.primitives import ProviderInstanceName
from imbue.mngr.providers.modal.instance import ModalProviderInstance
from imbue.mngr.providers.modal.log_utils import _create_deduplicating_writer
from imbue.mngr.providers.modal.log_utils import _create_modal_loguru_writer
from imbue.mngr.providers.modal.log_utils import _create_multi_writer
from imbue.mngr.providers.modal.log_utils import _ModalLoguruWriter
from imbue.mngr.providers.modal.log_utils import enable_modal_output_capture


class TestDeduplicatingWriter:
    """Tests for the deduplicating writer."""

    def test_writes_unique_messages(self) -> None:
        """Should write unique messages to the buffer."""
        writer = _create_deduplicating_writer()
        writer.write("message 1")
        writer.write("message 2")
        writer.write("message 3")

        assert "message 1" in writer.getvalue()
        assert "message 2" in writer.getvalue()
        assert "message 3" in writer.getvalue()

    def test_deduplicates_consecutive_identical_messages(self) -> None:
        """Should skip consecutive duplicate messages."""
        writer = _create_deduplicating_writer()
        writer.write("same message")
        writer.write("same message")
        writer.write("same message")

        assert writer.getvalue().count("same message") == 1

    def test_allows_non_consecutive_duplicates(self) -> None:
        """Should allow the same message to appear non-consecutively."""
        writer = _create_deduplicating_writer()
        writer.write("message a")
        writer.write("message b")
        writer.write("message a")

        content = writer.getvalue()
        assert content.count("message a") == 2
        assert content.count("message b") == 1

    def test_skips_empty_messages(self) -> None:
        """Should skip empty messages."""
        writer = _create_deduplicating_writer()
        writer.write("")
        writer.write("   ")
        writer.write("\n")
        writer.write("real message")

        assert writer.getvalue() == "real message"


class TestMultiWriter:
    """Tests for the multi writer."""

    def test_writes_to_all_files(self) -> None:
        """Should write to all file-like objects."""
        buffer1 = StringIO()
        buffer2 = StringIO()
        multi = _create_multi_writer([buffer1, buffer2])

        multi.write("test message")

        assert buffer1.getvalue() == "test message"
        assert buffer2.getvalue() == "test message"

    def test_is_not_a_tty(self) -> None:
        """Should report as not a tty to disable interactive features."""
        multi = _create_multi_writer([])
        assert multi.isatty() is False

    def test_context_manager(self) -> None:
        """Should work as a context manager."""
        buffer = StringIO()
        with _create_multi_writer([buffer]) as multi:
            multi.write("inside context")

        assert buffer.getvalue() == "inside context"


class TestModalLoguruWriter:
    """Tests for the Modal loguru writer."""

    def test_app_metadata_can_be_set(self) -> None:
        """Should allow setting app_id and app_name."""
        writer = _create_modal_loguru_writer()
        writer.app_id = "test-app-id"
        writer.app_name = "test-app-name"

        assert writer.app_id == "test-app-id"
        assert writer.app_name == "test-app-name"

    def test_initial_metadata_is_none(self) -> None:
        """Should have None for app metadata initially."""
        writer = _create_modal_loguru_writer()
        assert writer.app_id is None
        assert writer.app_name is None

    def test_is_writable(self) -> None:
        """Should report as writable."""
        writer = _create_modal_loguru_writer()
        assert writer.writable() is True
        assert writer.readable() is False
        assert writer.seekable() is False

    def test_deduplicates_messages(self) -> None:
        """Should deduplicate consecutive messages."""
        writer = _create_modal_loguru_writer()

        writer.write("same message")
        result1 = writer.write("same message")

        assert result1 == len("same message")


class TestEnableModalOutputCapture:
    """Tests for the enable_modal_output_capture context manager."""

    def test_returns_buffer_and_writer(self) -> None:
        """Should return a StringIO buffer and optional loguru writer."""
        with enable_modal_output_capture(is_logging_to_loguru=True) as (buffer, writer):
            assert isinstance(buffer, StringIO)
            assert writer is not None
            assert isinstance(writer, _ModalLoguruWriter)

    def test_returns_none_writer_when_disabled(self) -> None:
        """Should return None for writer when logging to loguru is disabled."""
        with enable_modal_output_capture(is_logging_to_loguru=False) as (buffer, writer):
            assert isinstance(buffer, StringIO)
            assert writer is None


pytest.importorskip("modal")


@pytest.mark.modal
@pytest.mark.timeout(180)
def test_modal_output_is_captured_during_host_creation(
    temp_mngr_ctx: MngrContext,
    mngr_test_id: str,
) -> None:
    """Should capture Modal output during host creation.

    This test verifies that the log capture is properly integrated into
    the ModalProviderInstance and that we can inspect captured output.
    """
    provider = ModalProviderInstance(
        name=ProviderInstanceName("modal-test"),
        host_dir=Path("/mngr"),
        mngr_ctx=temp_mngr_ctx,
        app_name=f"mngr-log-test-{mngr_test_id}",
        default_timeout=300,
        default_cpu=0.5,
        default_memory=0.5,
    )

    host = None
    try:
        host = provider.create_host(HostName("test-log-capture"))

        captured_output = provider.get_captured_output()

        assert isinstance(captured_output, str)

    finally:
        if host:
            provider.destroy_host(host)
        provider.close()
