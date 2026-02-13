import ast
import re
import subprocess
from datetime import datetime
from datetime import timezone
from functools import lru_cache
from pathlib import Path
from typing import Any
from typing import Self

from pydantic import Field
from pydantic import GetCoreSchemaHandler
from pydantic_core import CoreSchema
from pydantic_core import core_schema

from imbue.imbue_common.frozen_model import FrozenModel
from imbue.imbue_common.primitives import NonEmptyStr
from imbue.imbue_common.primitives import PositiveInt
from imbue.imbue_common.pure import pure


class FileExtension(NonEmptyStr):
    """A file extension including the leading dot (e.g., '.py', '.txt')."""

    def __new__(cls, value: str) -> Self:
        value = value.strip()
        if not value.startswith("."):
            value = f".{value}"
        return super().__new__(cls, value)


class RegexPattern(str):
    """A compiled regular expression pattern."""

    _compiled_pattern: re.Pattern[str]

    def __new__(cls, value: str, multiline: bool = False) -> Self:
        instance = super().__new__(cls, value)
        object.__setattr__(instance, "_multiline", multiline)
        return instance

    def __init__(self, value: str, multiline: bool = False) -> None:
        flags = re.MULTILINE if multiline else 0
        try:
            object.__setattr__(self, "_compiled_pattern", re.compile(value, flags))
        except re.error as e:
            raise ValueError(f"Invalid regex pattern: {value}") from e

    @property
    def compiled(self) -> re.Pattern[str]:
        return self._compiled_pattern

    @classmethod
    def __get_pydantic_core_schema__(
        cls,
        source_type: Any,
        handler: GetCoreSchemaHandler,
    ) -> CoreSchema:
        return core_schema.no_info_after_validator_function(
            cls,
            core_schema.str_schema(),
            serialization=core_schema.to_string_ser_schema(),
        )


class LineNumber(PositiveInt):
    """A line number in a file (1-indexed)."""


class RatchetMatchChunk(FrozenModel):
    """A chunk of text that matched a regex pattern in a file."""

    file_path: Path = Field(description="Path to the file containing the match")
    matched_content: str = Field(description="The content that matched the regex")
    start_line: LineNumber = Field(description="The starting line number (1-indexed)")
    end_line: LineNumber = Field(description="The ending line number (1-indexed)")
    last_modified_date: datetime = Field(description="The date this chunk was last modified in git")

    @property
    def matched_lines(self) -> str:
        contents = _read_file_contents(self.file_path)
        lines = contents.splitlines()
        return "\n".join(lines[self.start_line - 1 : self.end_line])


class RatchetsError(Exception):
    """Base exception for all ratchets-related errors."""


class GitCommandError(RatchetsError):
    """Raised when a git command fails."""


class FileReadError(RatchetsError):
    """Raised when a file cannot be read."""


@lru_cache(maxsize=None)
def _get_all_files_with_extension(
    folder_path: Path,
    extension: FileExtension,
) -> tuple[Path, ...]:
    """Get all non-git-ignored files with the specified extension in a folder (cached)."""
    try:
        result = subprocess.run(
            ["git", "ls-files", f"*{extension}"],
            cwd=folder_path,
            capture_output=True,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError as e:
        raise GitCommandError(f"Failed to list git-tracked files in {folder_path}") from e

    file_paths = [folder_path / line.strip() for line in result.stdout.splitlines() if line.strip()]
    return tuple(file_paths)


def _get_non_ignored_files_with_extension(
    folder_path: Path,
    extension: FileExtension,
    excluded_path_patterns: tuple[str, ...] = (),
) -> tuple[Path, ...]:
    """Get all non-git-ignored files with the specified extension in a folder.

    Each pattern in excluded_path_patterns is matched against file paths using Path.match(),
    which matches from the right for relative patterns (e.g., "test_*.py" matches any file
    whose name starts with "test_" regardless of directory depth).
    """
    file_paths = _get_all_files_with_extension(folder_path, extension)

    if excluded_path_patterns:
        file_paths = tuple(fp for fp in file_paths if not any(fp.match(pattern) for pattern in excluded_path_patterns))

    return file_paths


@lru_cache(maxsize=None)
def _read_file_contents(file_path: Path) -> str:
    """Read and cache file contents."""
    try:
        return file_path.read_text()
    except OSError as e:
        raise FileReadError(f"Cannot read file: {file_path}") from e


@lru_cache(maxsize=None)
def _parse_file_ast(file_path: Path) -> ast.Module | None:
    """Parse and cache the AST for a Python file. Returns None if parsing fails."""
    contents = _read_file_contents(file_path)
    try:
        return ast.parse(contents, filename=str(file_path))
    except SyntaxError:
        return None


def _get_line_commit_date(
    file_path: Path,
    line_number: LineNumber,
) -> datetime:
    """Get the date of the last commit that touched a specific line."""
    try:
        result = subprocess.run(
            ["git", "blame", "-L", f"{line_number},{line_number}", "--porcelain", str(file_path)],
            cwd=file_path.parent,
            capture_output=True,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError as e:
        raise GitCommandError(f"Failed to get git blame for {file_path}:{line_number}") from e

    # Parse the porcelain output to extract the committer-time
    for line in result.stdout.splitlines():
        if line.startswith("committer-time "):
            timestamp_str = line.split(" ", 1)[1]
            timestamp = int(timestamp_str)
            return datetime.fromtimestamp(timestamp, tz=timezone.utc)

    raise GitCommandError(f"Could not find commit date for {file_path}:{line_number}")


def _get_chunk_commit_date(
    file_path: Path,
    start_line: LineNumber,
    end_line: LineNumber,
) -> datetime:
    """Get the most recent commit date for any line in a chunk."""
    most_recent_date = datetime.min.replace(tzinfo=timezone.utc)

    for line_idx in range(start_line, end_line + 1):
        line_date = _get_line_commit_date(file_path, LineNumber(line_idx))
        if line_date > most_recent_date:
            most_recent_date = line_date

    return most_recent_date


@pure
def get_ratchet_failures(
    folder_path: Path,
    extension: FileExtension,
    pattern: RegexPattern,
    excluded_path_patterns: tuple[str, ...] = (),
) -> tuple[RatchetMatchChunk, ...]:
    """Find all regex matches in git-tracked files and return them sorted by modification date.

    This function applies a regex pattern to all non-git-ignored files with the specified
    extension in the given folder. For each match, it determines the date of the last commit
    that touched any line in the match and returns all matches sorted from most recently
    changed to least recently changed.

    File contents are transparently cached to avoid repeated reads when called multiple times.
    """
    # Get all relevant files
    file_paths = _get_non_ignored_files_with_extension(folder_path, extension, excluded_path_patterns)

    chunks: list[RatchetMatchChunk] = []

    # Process each file
    for file_path in file_paths:
        # Read file contents (cached)
        file_contents = _read_file_contents(file_path)

        # Find all matches
        for match in pattern.compiled.finditer(file_contents):
            matched_text = match.group(0)

            # Calculate line numbers for the match
            start_pos = match.start()

            # Count newlines before the match to get start line
            start_line_number = file_contents[:start_pos].count("\n") + 1

            # Count newlines within the match to get end line
            end_line_number = start_line_number + matched_text.count("\n")

            # Get the commit date for this chunk
            commit_date = _get_chunk_commit_date(
                file_path,
                LineNumber(start_line_number),
                LineNumber(end_line_number),
            )

            # Create the chunk
            chunk = RatchetMatchChunk(
                file_path=file_path,
                matched_content=matched_text,
                start_line=LineNumber(start_line_number),
                end_line=LineNumber(end_line_number),
                last_modified_date=commit_date,
            )
            chunks.append(chunk)

    # Sort by most recently changed first
    sorted_chunks = sorted(
        chunks,
        key=lambda c: c.last_modified_date,
        reverse=True,
    )

    return tuple(sorted_chunks)


def clear_ratchet_caches() -> None:
    """Clear all LRU caches used by ratchet testing to free memory.

    Call this after all ratchet tests have completed to release cached file contents,
    AST trees, and file listings. This prevents the ratchet test worker from holding
    large amounts of memory that could contribute to resource pressure when the worker
    runs subsequent non-ratchet tests.
    """
    _get_all_files_with_extension.cache_clear()
    _read_file_contents.cache_clear()
    _parse_file_ast.cache_clear()


@pure
def format_ratchet_failure_message(
    rule_name: str,
    rule_description: str,
    chunks: tuple[RatchetMatchChunk, ...],
    max_display_count: int = 5,
) -> str:
    """Format a detailed failure message for a ratchet test violation."""
    if not chunks:
        return f"No {rule_name} found (this is good!)"

    # Get the most recent violations (chunks are already sorted by most recent first)
    recent_violations = chunks[:max_display_count]

    lines = [
        "\n",
        "=" * 80,
        f"RATCHET TEST FAILURE: {rule_name} have increased!",
        "=" * 80,
        "",
        f"Rule: {rule_description}",
        "",
        f"Current count: {len(chunks)}",
        "",
        f"Most recent violations (up to {max_display_count}):",
        "",
    ]

    for idx, chunk in enumerate(recent_violations, 1):
        # Make path relative to a reasonable base for readability
        try:
            # Try to make path relative to project root (4 levels up from typical location)
            relative_path = chunk.file_path.relative_to(chunk.file_path.parents[4])
        except (ValueError, IndexError):
            # Fall back to absolute path if relative doesn't work
            relative_path = chunk.file_path

        lines.extend(
            [
                f"{idx}. {relative_path}:{chunk.start_line}",
                f"   Last modified: {chunk.last_modified_date.strftime('%Y-%m-%d %H:%M:%S UTC')}",
                f"   Content lines:\n{chunk.matched_lines}",
                "",
            ]
        )

    lines.extend(
        [
            "=" * 80,
            "What to do: fix the violation and remove the offending code",
            "=" * 80,
        ]
    )

    return "\n".join(lines)


@pure
def check_regex_ratchet(
    source_dir: Path,
    extension: FileExtension,
    pattern: RegexPattern,
    excluded_path_patterns: tuple[str, ...] = (),
) -> tuple[RatchetMatchChunk, ...]:
    """Check a regex-based ratchet and return all matching chunks."""
    return get_ratchet_failures(source_dir, extension, pattern, excluded_path_patterns)
