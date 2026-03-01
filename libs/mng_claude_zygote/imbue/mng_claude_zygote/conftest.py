from pathlib import Path
from typing import Any

import pytest


class StubCommandResult:
    """Concrete test double for command execution results."""

    def __init__(self, *, success: bool = True, stderr: str = "", stdout: str = "") -> None:
        self.success = success
        self.stderr = stderr
        self.stdout = stdout


class StubHost:
    """Concrete test double for OnlineHostInterface that records operations.

    Records all execute_command calls and write_file/write_text_file calls
    for assertion in tests. Supports optional text_file_contents for
    read_text_file stubbing.
    """

    def __init__(
        self,
        host_dir: Path = Path("/tmp/mng-test/host"),
        command_results: dict[str, StubCommandResult] | None = None,
        text_file_contents: dict[str, str] | None = None,
    ) -> None:
        self.host_dir = host_dir
        self.executed_commands: list[str] = []
        self.written_files: list[tuple[Path, bytes, str]] = []
        self.written_text_files: list[tuple[Path, str]] = []
        self._command_results = command_results or {}
        self._text_file_contents = text_file_contents or {}

    def execute_command(self, command: str, **kwargs: Any) -> StubCommandResult:
        self.executed_commands.append(command)
        for pattern, result in self._command_results.items():
            if pattern in command:
                return result
        # For `cd <path> && pwd`, return the path as stdout
        if "&& pwd" in command and "cd " in command:
            path = command.split("cd ")[1].split(" &&")[0].strip("'\"")
            return StubCommandResult(stdout=path + "\n")
        return StubCommandResult()

    def read_text_file(self, path: Path) -> str:
        for pattern, content in self._text_file_contents.items():
            if pattern in str(path):
                return content
        raise FileNotFoundError(f"No stub content for {path}")

    def write_file(self, path: Path, content: bytes, mode: str = "0644") -> None:
        self.written_files.append((path, content, mode))

    def write_text_file(self, path: Path, content: str) -> None:
        self.written_text_files.append((path, content))


@pytest.fixture()
def stub_host() -> StubHost:
    """Provide a fresh StubHost instance."""
    return StubHost()
