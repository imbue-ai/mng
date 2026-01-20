"""Example usage of the ratchets module to find TODOs in Python files."""

from pathlib import Path

from imbue.imbue_common.ratchet_testing.core import FileExtension
from imbue.imbue_common.ratchet_testing.core import RegexPattern
from imbue.imbue_common.ratchet_testing.core import get_ratchet_failures


def main() -> None:
    # Find all TODO comments in Python files in the current directory
    folder_path = Path.cwd()
    extension = FileExtension(".py")
    pattern = RegexPattern(r"# TODO:.*")

    chunks = get_ratchet_failures(folder_path, extension, pattern)

    # Print results sorted by most recently changed first
    for chunk in chunks:
        print(f"\n{chunk.file_path}:{chunk.start_line}")
        print(f"  Last modified: {chunk.last_modified_date}")
        print(f"  Content: {chunk.matched_content}")


if __name__ == "__main__":
    main()
