import json
import subprocess
import tempfile
from abc import ABC
from abc import abstractmethod
from collections.abc import Iterator
from collections.abc import Sequence
from pathlib import Path
from typing import Final

from pydantic import Field

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
    """Runs claude in a subprocess with streaming.

    By default, runs from an empty temp directory with all tools disabled (safe
    for untrusted prompts). Set allowed_tools and working_directory to grant
    read-only file access for agentic exploration.
    """

    allowed_tools: tuple[str, ...] = Field(
        default=(),
        frozen=True,
        description="Tool names to allow (empty disables all tools)",
    )
    working_directory: Path | None = Field(
        default=None,
        frozen=True,
        description="Working directory for claude (None uses a temp directory)",
    )

    def query(self, prompt: str, system_prompt: str) -> Iterator[str]:
        cmd = _build_claude_command(
            prompt=prompt,
            system_prompt=system_prompt,
            allowed_tools=self.allowed_tools,
        )

        if self.working_directory is not None:
            yield from _run_claude_process(cmd, cwd=self.working_directory)
        else:
            with tempfile.TemporaryDirectory(prefix="mngr-claude-") as tmp_dir:
                yield from _run_claude_process(cmd, cwd=Path(tmp_dir))


@pure
def _build_claude_command(
    prompt: str,
    system_prompt: str,
    allowed_tools: Sequence[str],
) -> list[str]:
    cmd = [
        "claude",
        "--print",
        "--system-prompt",
        system_prompt,
        "--output-format",
        "stream-json",
        "--verbose",
        "--include-partial-messages",
        "--no-session-persistence",
    ]

    if allowed_tools:
        cmd.extend(["--allowedTools", ",".join(allowed_tools)])
    else:
        cmd.extend(["--tools", ""])

    # Use -- to separate flags from the positional prompt, since variadic
    # flags like --allowedTools can consume subsequent positional args
    cmd.append("--")
    cmd.append(prompt)
    return cmd


def _run_claude_process(cmd: Sequence[str], cwd: Path) -> Iterator[str]:
    """Spawn a claude subprocess and yield text delta chunks."""
    try:
        process = subprocess.Popen(
            list(cmd),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.DEVNULL,
            text=True,
            cwd=str(cwd),
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
