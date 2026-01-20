import subprocess
import time
from datetime import datetime
from datetime import timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from imbue.imbue_common.ratchet_testing.core import FileExtension
from imbue.imbue_common.ratchet_testing.core import GitCommandError
from imbue.imbue_common.ratchet_testing.core import LineNumber
from imbue.imbue_common.ratchet_testing.core import RatchetMatchChunk
from imbue.imbue_common.ratchet_testing.core import RegexPattern
from imbue.imbue_common.ratchet_testing.core import _get_non_ignored_files_with_extension
from imbue.imbue_common.ratchet_testing.core import _read_file_contents
from imbue.imbue_common.ratchet_testing.core import format_ratchet_failure_message
from imbue.imbue_common.ratchet_testing.core import get_ratchet_failures


def test_file_extension_with_dot() -> None:
    ext = FileExtension(".py")
    assert ext == ".py"


def test_file_extension_without_dot() -> None:
    ext = FileExtension("py")
    assert ext == ".py"


def test_file_extension_trims_whitespace() -> None:
    ext = FileExtension("  .txt  ")
    assert ext == ".txt"


def test_regex_pattern_compiles_valid_pattern() -> None:
    pattern = RegexPattern(r"\d+")
    assert pattern.compiled.pattern == r"\d+"


def test_regex_pattern_raises_on_invalid_pattern() -> None:
    with pytest.raises(ValueError, match="Invalid regex pattern"):
        RegexPattern(r"[invalid(")


def test_regex_pattern_can_find_matches() -> None:
    pattern = RegexPattern(r"\d+")
    matches = list(pattern.compiled.finditer("abc 123 def 456"))
    assert len(matches) == 2
    assert matches[0].group() == "123"
    assert matches[1].group() == "456"


def test_line_number_must_be_positive() -> None:
    line = LineNumber(1)
    assert line == 1


def test_line_number_rejects_zero() -> None:
    with pytest.raises(ValueError):
        LineNumber(0)


def test_line_number_rejects_negative() -> None:
    with pytest.raises(ValueError):
        LineNumber(-1)


def test_ratchet_match_chunk_creation() -> None:
    chunk = RatchetMatchChunk(
        file_path=Path("/tmp/test.py"),
        matched_content="def foo():\n    pass",
        start_line=LineNumber(10),
        end_line=LineNumber(11),
        last_modified_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
    )
    assert chunk.file_path == Path("/tmp/test.py")
    assert chunk.start_line == 10
    assert chunk.end_line == 11


def test_ratchet_match_chunk_is_frozen() -> None:
    chunk = RatchetMatchChunk(
        file_path=Path("/tmp/test.py"),
        matched_content="test",
        start_line=LineNumber(1),
        end_line=LineNumber(1),
        last_modified_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
    )
    with pytest.raises(ValidationError):
        chunk.start_line = LineNumber(2)


def test_get_non_ignored_files_returns_matching_files(tmp_path: Path) -> None:
    test_dir = tmp_path / "test_repo"
    test_dir.mkdir()

    # Initialize git repo
    subprocess.run(["git", "init"], cwd=test_dir, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=test_dir,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=test_dir,
        check=True,
        capture_output=True,
    )

    # Create test files
    (test_dir / "file1.py").write_text("print('hello')")
    (test_dir / "file2.py").write_text("print('world')")
    (test_dir / "file3.txt").write_text("text file")

    # Add files to git
    subprocess.run(["git", "add", "."], cwd=test_dir, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "Initial commit"],
        cwd=test_dir,
        check=True,
        capture_output=True,
    )

    # Call the function
    result = _get_non_ignored_files_with_extension(test_dir, FileExtension(".py"))

    assert len(result) == 2
    assert all(path.suffix == ".py" for path in result)


def test_get_non_ignored_files_excludes_specified_file(tmp_path: Path) -> None:
    test_dir = tmp_path / "test_repo"
    test_dir.mkdir()

    # Initialize git repo
    subprocess.run(["git", "init"], cwd=test_dir, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=test_dir,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=test_dir,
        check=True,
        capture_output=True,
    )

    # Create test files
    file1 = test_dir / "file1.py"
    file2 = test_dir / "file2.py"
    file1.write_text("print('hello')")
    file2.write_text("print('world')")

    # Add files to git
    subprocess.run(["git", "add", "."], cwd=test_dir, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "Initial commit"],
        cwd=test_dir,
        check=True,
        capture_output=True,
    )

    # Call without exclusion - should get both files
    result_without_exclusion = _get_non_ignored_files_with_extension(test_dir, FileExtension(".py"))
    assert len(result_without_exclusion) == 2

    # Call with exclusion - should get only one file
    result_with_exclusion = _get_non_ignored_files_with_extension(test_dir, FileExtension(".py"), file1)
    assert len(result_with_exclusion) == 1
    assert result_with_exclusion[0].resolve() == file2.resolve()


def test_read_file_contents_caches_results(tmp_path: Path) -> None:
    test_file = tmp_path / "test.txt"
    test_file.write_text("original content")

    # First read
    content1 = _read_file_contents(test_file)
    # Second read should return cached result even if file changes
    test_file.write_text("modified content")
    content2 = _read_file_contents(test_file)

    assert content1 == "original content"
    assert content1 is content2


def test_get_ratchet_failures_finds_matches_in_git_repo(tmp_path: Path) -> None:
    test_dir = tmp_path / "test_repo"
    test_dir.mkdir()

    # Initialize git repo
    subprocess.run(["git", "init"], cwd=test_dir, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=test_dir,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=test_dir,
        check=True,
        capture_output=True,
    )

    # Create test file with pattern matches
    test_file = test_dir / "test.py"
    test_file.write_text("# TODO: Fix this\ndef foo():\n    pass\n# TODO: And this\ndef bar():\n    pass\n")

    # Add and commit
    subprocess.run(["git", "add", "."], cwd=test_dir, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "Add test file"],
        cwd=test_dir,
        check=True,
        capture_output=True,
    )

    # Find TODO comments
    pattern = RegexPattern(r"# TODO:.*")
    chunks = get_ratchet_failures(test_dir, FileExtension(".py"), pattern)

    assert len(chunks) == 2
    assert chunks[0].matched_content in ["# TODO: Fix this", "# TODO: And this"]
    assert chunks[1].matched_content in ["# TODO: Fix this", "# TODO: And this"]
    assert all(chunk.file_path.name == "test.py" for chunk in chunks)
    assert all(isinstance(chunk.last_modified_date, datetime) for chunk in chunks)
    assert all(chunk.last_modified_date.tzinfo == timezone.utc for chunk in chunks)


def test_get_ratchet_failures_sorts_by_most_recent_first(tmp_path: Path) -> None:
    test_dir = tmp_path / "test_repo"
    test_dir.mkdir()

    subprocess.run(["git", "init"], cwd=test_dir, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=test_dir,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=test_dir,
        check=True,
        capture_output=True,
    )

    # Create file with first TODO
    test_file = test_dir / "test.py"
    test_file.write_text("# TODO: Old issue\n")
    subprocess.run(["git", "add", "."], cwd=test_dir, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "First commit"],
        cwd=test_dir,
        check=True,
        capture_output=True,
    )

    # Wait to ensure different timestamps
    time.sleep(1)

    # Add second TODO
    test_file.write_text("# TODO: Old issue\n# TODO: New issue\n")
    subprocess.run(["git", "add", "."], cwd=test_dir, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "Second commit"],
        cwd=test_dir,
        check=True,
        capture_output=True,
    )

    pattern = RegexPattern(r"# TODO:.*")
    chunks = get_ratchet_failures(test_dir, FileExtension(".py"), pattern)

    # Most recent should be first
    assert len(chunks) == 2
    assert chunks[0].last_modified_date > chunks[1].last_modified_date
    assert chunks[0].matched_content == "# TODO: New issue"


def test_get_ratchet_failures_handles_multiline_matches(tmp_path: Path) -> None:
    test_dir = tmp_path / "test_repo"
    test_dir.mkdir()

    subprocess.run(["git", "init"], cwd=test_dir, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=test_dir,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=test_dir,
        check=True,
        capture_output=True,
    )

    test_file = test_dir / "test.py"
    test_file.write_text("def foo():\n    pass\n\ndef bar():\n    pass\n")

    subprocess.run(["git", "add", "."], cwd=test_dir, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "Add functions"],
        cwd=test_dir,
        check=True,
        capture_output=True,
    )

    # Match function definitions (multiline)
    pattern = RegexPattern(r"def \w+\(\):\n    pass")
    chunks = get_ratchet_failures(test_dir, FileExtension(".py"), pattern)

    assert len(chunks) == 2
    assert all("\n" in chunk.matched_content for chunk in chunks)
    assert chunks[0].end_line - chunks[0].start_line == 1
    assert chunks[1].end_line - chunks[1].start_line == 1


def test_get_ratchet_failures_returns_empty_for_no_matches(tmp_path: Path) -> None:
    test_dir = tmp_path / "test_repo"
    test_dir.mkdir()

    subprocess.run(["git", "init"], cwd=test_dir, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=test_dir,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=test_dir,
        check=True,
        capture_output=True,
    )

    test_file = test_dir / "test.py"
    test_file.write_text("print('hello world')\n")

    subprocess.run(["git", "add", "."], cwd=test_dir, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "Add file"],
        cwd=test_dir,
        check=True,
        capture_output=True,
    )

    pattern = RegexPattern(r"# TODO:.*")
    chunks = get_ratchet_failures(test_dir, FileExtension(".py"), pattern)

    assert len(chunks) == 0


def test_get_ratchet_failures_only_processes_specified_extension(tmp_path: Path) -> None:
    test_dir = tmp_path / "test_repo"
    test_dir.mkdir()

    subprocess.run(["git", "init"], cwd=test_dir, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=test_dir,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=test_dir,
        check=True,
        capture_output=True,
    )

    (test_dir / "file.py").write_text("# TODO: Python file\n")
    (test_dir / "file.txt").write_text("# TODO: Text file\n")

    subprocess.run(["git", "add", "."], cwd=test_dir, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "Add files"],
        cwd=test_dir,
        check=True,
        capture_output=True,
    )

    pattern = RegexPattern(r"# TODO:.*")
    chunks = get_ratchet_failures(test_dir, FileExtension(".py"), pattern)

    assert len(chunks) == 1
    assert chunks[0].file_path.suffix == ".py"


def test_get_ratchet_failures_raises_on_non_git_directory(tmp_path: Path) -> None:
    test_dir = tmp_path / "not_a_repo"
    test_dir.mkdir()

    (test_dir / "file.py").write_text("# TODO: Test\n")

    pattern = RegexPattern(r"# TODO:.*")

    with pytest.raises(GitCommandError):
        get_ratchet_failures(test_dir, FileExtension(".py"), pattern)


def test_formatting():
    format_ratchet_failure_message(
        rule_name="Test Rule",
        rule_description="This is a test rule for demonstration purposes.",
        chunks=(
            RatchetMatchChunk(
                file_path=Path(__file__),
                start_line=LineNumber(42),
                end_line=LineNumber(43),
                matched_content="    suspicious_code_here()\n    another_bad_line()",
                last_modified_date=datetime(2024, 6, 1, 12, 0, 0),
            ),
        ),
        max_display_count=3,
    )
