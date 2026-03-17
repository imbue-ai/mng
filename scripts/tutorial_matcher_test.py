from pathlib import Path
from textwrap import dedent

from scripts.tutorial_matcher import block_matches_docstring
from scripts.tutorial_matcher import find_pytest_functions
from scripts.tutorial_matcher import parse_script_blocks


def test_parse_discards_shebang_block(tmp_path: Path) -> None:
    script = tmp_path / "test.sh"
    script.write_text("#!/bin/bash\nset -euo pipefail\n\nmng foo\n")
    blocks = parse_script_blocks(script)
    assert blocks == ["mng foo"]


def test_parse_keeps_first_block_without_shebang(tmp_path: Path) -> None:
    script = tmp_path / "test.sh"
    script.write_text("mng foo\n\nmng bar\n")
    blocks = parse_script_blocks(script)
    assert blocks == ["mng foo", "mng bar"]


def test_parse_discards_comment_only_blocks(tmp_path: Path) -> None:
    script = tmp_path / "test.sh"
    script.write_text("# just a comment\n# another comment\n\nmng foo\n")
    blocks = parse_script_blocks(script)
    assert blocks == ["mng foo"]


def test_parse_keeps_blocks_with_comments_and_commands(tmp_path: Path) -> None:
    script = tmp_path / "test.sh"
    script.write_text("# do the thing\nmng foo\n\nmng bar\n")
    blocks = parse_script_blocks(script)
    assert blocks == ["# do the thing\nmng foo", "mng bar"]


def test_parse_skips_empty_blocks(tmp_path: Path) -> None:
    script = tmp_path / "test.sh"
    script.write_text("mng foo\n\n\n\nmng bar\n")
    blocks = parse_script_blocks(script)
    assert blocks == ["mng foo", "mng bar"]


def test_block_matches_indented_docstring() -> None:
    block = "# test foo\nmng foo"
    docstring = "    # test foo\n    mng foo\n    "
    assert block_matches_docstring(block, docstring)


def test_block_does_not_match_different_docstring() -> None:
    block = "mng foo"
    docstring = "    mng bar\n    "
    assert not block_matches_docstring(block, docstring)


def test_block_matches_docstring_with_extra_content() -> None:
    block = "mng foo"
    docstring = "    mng foo\n\n    Some extra explanation."
    assert block_matches_docstring(block, docstring)


def test_find_pytest_functions_discovers_test_funcs(tmp_path: Path) -> None:
    test_file = tmp_path / "test_example.py"
    test_file.write_text(
        dedent("""\
        def test_something():
            \"\"\"
            mng foo
            \"\"\"
            pass

        def helper():
            pass

        def test_other():
            pass
        """)
    )
    funcs = find_pytest_functions(tmp_path)
    names = [sig.split("(")[0] for sig, _, _ in funcs]
    assert names == ["def test_something", "def test_other"]


def test_find_pytest_functions_returns_docstrings(tmp_path: Path) -> None:
    test_file = tmp_path / "test_example.py"
    test_file.write_text(
        dedent("""\
        def test_with_doc():
            \"\"\"
            mng foo
            \"\"\"
            pass

        def test_no_doc():
            pass
        """)
    )
    funcs = find_pytest_functions(tmp_path)
    assert funcs[0][1] is not None
    assert "mng foo" in funcs[0][1]
    assert funcs[1][1] is None


def test_find_pytest_functions_warns_on_syntax_error(tmp_path: Path, capsys: object) -> None:
    bad_file = tmp_path / "test_bad.py"
    bad_file.write_text("def test_broken(:\n    pass\n")
    funcs = find_pytest_functions(tmp_path)
    assert funcs == []


def test_find_pytest_functions_recurses_subdirs(tmp_path: Path) -> None:
    subdir = tmp_path / "sub"
    subdir.mkdir()
    test_file = subdir / "test_nested.py"
    test_file.write_text("def test_nested():\n    pass\n")
    funcs = find_pytest_functions(tmp_path)
    assert len(funcs) == 1
    assert "test_nested" in funcs[0][0]
