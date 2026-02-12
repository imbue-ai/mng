import json
import subprocess
import tempfile
from abc import ABC
from abc import abstractmethod
from collections.abc import Iterator
from typing import Final

from imbue.imbue_common.mutable_model import MutableModel
from imbue.imbue_common.pure import pure
from imbue.mngr.errors import MngrError

_PROCESS_WAIT_TIMEOUT_SECONDS: Final[int] = 10


class ClaudeBackendInterface(MutableModel, ABC):
    """Abstraction over the claude subprocess for testability."""

    @abstractmethod
    def query(self, prompt: str, system_prompt: str) -> Iterator[str]:
        """Send a prompt to claude and yield response text chunks."""


@pure
def _extract_text_delta(line: str) -> str | None:
    """Extract text from a stream-json content_block_delta event.

    Returns the delta text if the line is a content_block_delta with a text_delta,
    or None otherwise.
    """
    try:
        parsed = json.loads(line)
    except (json.JSONDecodeError, ValueError):
        return None

    if parsed.get("type") != "stream_event":
        return None

    event = parsed.get("event")
    if not isinstance(event, dict):
        return None

    if event.get("type") != "content_block_delta":
        return None

    delta = event.get("delta")
    if not isinstance(delta, dict):
        return None

    if delta.get("type") != "text_delta":
        return None

    text = delta.get("text")
    if isinstance(text, str):
        return text

    return None


class SubprocessClaudeBackend(ClaudeBackendInterface):
    """Runs claude in a subprocess from an empty temp directory with streaming."""

    def query(self, prompt: str, system_prompt: str) -> Iterator[str]:
        with tempfile.TemporaryDirectory(prefix="mngr-claude-") as tmp_dir:
            try:
                process = subprocess.Popen(
                    [
                        "claude",
                        "--print",
                        "--system-prompt",
                        system_prompt,
                        "--output-format",
                        "stream-json",
                        "--verbose",
                        "--include-partial-messages",
                        "--tools",
                        "",
                        "--no-session-persistence",
                        prompt,
                    ],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    stdin=subprocess.DEVNULL,
                    text=True,
                    cwd=tmp_dir,
                )
            except FileNotFoundError:
                raise MngrError(
                    "claude is not installed or not found in PATH. "
                    "Install Claude Code: https://docs.anthropic.com/en/docs/claude-code/overview"
                ) from None

            assert process.stdout is not None

            try:
                # Stream text deltas from stdout
                is_error = False
                for line in process.stdout:
                    stripped = line.strip()
                    if not stripped:
                        continue

                    # Check for result events that indicate completion status
                    try:
                        parsed = json.loads(stripped)
                        if parsed.get("type") == "result" and parsed.get("is_error"):
                            is_error = True
                    except (json.JSONDecodeError, ValueError):
                        pass

                    text = _extract_text_delta(stripped)
                    if text is not None:
                        yield text

                # Wait for process to finish and check exit code
                process.wait(timeout=_PROCESS_WAIT_TIMEOUT_SECONDS)

                if is_error or process.returncode != 0:
                    assert process.stderr is not None
                    stderr_content = process.stderr.read().strip()
                    detail = stderr_content or "unknown error (no output captured)"
                    raise MngrError(f"claude failed (exit code {process.returncode}): {detail}")
            finally:
                # Ensure the subprocess is cleaned up if the generator exits early
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=_PROCESS_WAIT_TIMEOUT_SECONDS)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()


def accumulate_chunks(chunks: Iterator[str]) -> str:
    """Accumulate all chunks from an iterator into a single string."""
    parts: list[str] = []
    for chunk in chunks:
        parts.append(chunk)
    return "".join(parts)
