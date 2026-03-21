from imbue.mng_file.data_types import FileEntry
from imbue.mng_file.data_types import PathRelativeTo


def test_path_relative_to_values() -> None:
    assert PathRelativeTo.WORK.value == "WORK"
    assert PathRelativeTo.STATE.value == "STATE"
    assert PathRelativeTo.HOST.value == "HOST"


def test_file_entry_with_all_fields() -> None:
    entry = FileEntry(
        name="config.toml",
        path="/home/user/config.toml",
        file_type="file",
        size=256,
        modified="2026-03-21T12:00:00+00:00",
        permissions="-rw-r--r--",
    )
    assert entry.name == "config.toml"
    assert entry.size == 256


def test_file_entry_with_optional_fields_none() -> None:
    entry = FileEntry(
        name="dir",
        path="/home/user/dir",
        file_type="directory",
        size=None,
        modified=None,
        permissions=None,
    )
    assert entry.size is None
    assert entry.modified is None
    assert entry.permissions is None
