import subprocess
from pathlib import Path

import pytest
from inline_snapshot import snapshot

from imbue.imbue_common.ratchet_testing.core import FileExtension
from imbue.imbue_common.ratchet_testing.core import RegexPattern
from imbue.imbue_common.ratchet_testing.core import check_regex_ratchet
from imbue.imbue_common.ratchet_testing.core import clear_ratchet_caches
from imbue.imbue_common.ratchet_testing.core import format_ratchet_failure_message
from imbue.imbue_common.ratchet_testing.ratchets import _is_test_file
from imbue.imbue_common.ratchet_testing.ratchets import find_assert_isinstance_usages
from imbue.imbue_common.ratchet_testing.ratchets import find_cast_usages
from imbue.imbue_common.ratchet_testing.ratchets import find_if_elif_without_else
from imbue.imbue_common.ratchet_testing.ratchets import find_init_methods_in_non_exception_classes
from imbue.imbue_common.ratchet_testing.ratchets import find_inline_functions
from imbue.imbue_common.ratchet_testing.ratchets import find_underscore_imports

# Exclude this test file from ratchet scans to prevent self-referential matches
_THIS_FILE = Path(__file__)

# Group all ratchet tests onto a single xdist worker to benefit from LRU caching
pytestmark = pytest.mark.xdist_group(name="ratchets")


def teardown_module() -> None:
    """Clear ratchet LRU caches after all tests in this module complete.

    The ratchet testing functions use unbounded LRU caches for file contents, AST trees,
    and file listings. Clearing these after the ratchet tests frees memory for any
    subsequent tests that may run on this xdist worker, reducing resource pressure.
    """
    clear_ratchet_caches()


def _get_mngr_source_dir() -> Path:
    return Path(__file__).parent.parent


def test_prevent_todos() -> None:
    pattern = RegexPattern(r"# TODO:.*")
    chunks = check_regex_ratchet(_get_mngr_source_dir(), FileExtension(".py"), pattern, _THIS_FILE)

    # TODO and FIXME should only be added by a human; this is intended to catch TODOs added by an agent
    assert len(chunks) <= snapshot(2), format_ratchet_failure_message(
        rule_name="TODO comments",
        rule_description="TODO comments should not increase (ideally should decrease to zero)",
        chunks=chunks,
    )


def test_prevent_exec_usage() -> None:
    # Negative lookbehind to allow .exec() method calls (e.g., sandbox.exec())
    pattern = RegexPattern(r"(?<!\.)\bexec\s*\(")
    chunks = check_regex_ratchet(_get_mngr_source_dir(), FileExtension(".py"), pattern, _THIS_FILE)

    assert len(chunks) <= snapshot(0), format_ratchet_failure_message(
        rule_name="exec() usages",
        rule_description="exec() should not be used due to security and maintainability concerns",
        chunks=chunks,
    )


def test_prevent_eval_usage() -> None:
    pattern = RegexPattern(r"\beval\s*\(")
    chunks = check_regex_ratchet(_get_mngr_source_dir(), FileExtension(".py"), pattern, _THIS_FILE)

    assert len(chunks) <= snapshot(0), format_ratchet_failure_message(
        rule_name="eval() usages",
        rule_description="eval() should not be used due to security and maintainability concerns",
        chunks=chunks,
    )


def test_prevent_inline_imports() -> None:
    # Note: interfaces/agent.py uses TYPE_CHECKING for imports from interfaces/host.py
    # to avoid circular imports. This is the only accepted location (per comment in that file).
    pattern = RegexPattern(r"^[ \t]+import\s+\w+|^[ \t]+from\s+\S+\s+import\b", multiline=True)
    chunks = check_regex_ratchet(_get_mngr_source_dir(), FileExtension(".py"), pattern, _THIS_FILE)

    assert len(chunks) <= snapshot(2), format_ratchet_failure_message(
        rule_name="inline imports",
        rule_description="Imports should be at the top of the file, not inline within functions",
        chunks=chunks,
    )


def test_prevent_bare_except() -> None:
    pattern = RegexPattern(r"except\s*:")
    chunks = check_regex_ratchet(_get_mngr_source_dir(), FileExtension(".py"), pattern, _THIS_FILE)

    assert len(chunks) <= snapshot(0), format_ratchet_failure_message(
        rule_name="bare except clauses",
        rule_description="Bare 'except:' catches all exceptions including system exits. Use specific exception types instead",
        chunks=chunks,
    )


def test_prevent_broad_exception_catch() -> None:
    pattern = RegexPattern(r"except\s+Exception\b")
    chunks = check_regex_ratchet(_get_mngr_source_dir(), FileExtension(".py"), pattern, _THIS_FILE)

    assert len(chunks) <= snapshot(2), format_ratchet_failure_message(
        rule_name="except Exception catches",
        rule_description="Catching 'Exception' is too broad. Use specific exception types instead",
        chunks=chunks,
    )


def test_prevent_base_exception_catch() -> None:
    pattern = RegexPattern(r"except\s+BaseException\b")
    chunks = check_regex_ratchet(_get_mngr_source_dir(), FileExtension(".py"), pattern, _THIS_FILE)

    assert len(chunks) <= snapshot(1), format_ratchet_failure_message(
        rule_name="except BaseException catches",
        rule_description="Catching 'BaseException' catches system exits and keyboard interrupts. Use specific exception types instead",
        chunks=chunks,
    )


def test_prevent_while_true() -> None:
    pattern = RegexPattern(r"\bwhile\s+True\s*:")
    chunks = check_regex_ratchet(_get_mngr_source_dir(), FileExtension(".py"), pattern, _THIS_FILE)

    assert len(chunks) <= snapshot(0), format_ratchet_failure_message(
        rule_name="while True loops",
        rule_description="'while True' loops can cause infinite loops and make code harder to reason about. Use explicit conditions instead",
        chunks=chunks,
    )


def test_prevent_asyncio_import() -> None:
    pattern = RegexPattern(r"\bimport\s+asyncio\b|\bfrom\s+asyncio\b")
    chunks = check_regex_ratchet(_get_mngr_source_dir(), FileExtension(".py"), pattern, _THIS_FILE)

    assert len(chunks) <= snapshot(0), format_ratchet_failure_message(
        rule_name="asyncio imports",
        rule_description="asyncio is banned per style guide. Use synchronous code instead",
        chunks=chunks,
    )


def test_prevent_pandas_import() -> None:
    pattern = RegexPattern(r"\bimport\s+pandas\b|\bfrom\s+pandas\b")
    chunks = check_regex_ratchet(_get_mngr_source_dir(), FileExtension(".py"), pattern, _THIS_FILE)

    assert len(chunks) <= snapshot(0), format_ratchet_failure_message(
        rule_name="pandas imports",
        rule_description="pandas is banned per style guide. Use polars instead",
        chunks=chunks,
    )


def test_prevent_dataclasses_import() -> None:
    pattern = RegexPattern(r"\bimport\s+dataclasses\b|\bfrom\s+dataclasses\b")
    chunks = check_regex_ratchet(_get_mngr_source_dir(), FileExtension(".py"), pattern, _THIS_FILE)

    assert len(chunks) <= snapshot(0), format_ratchet_failure_message(
        rule_name="dataclasses imports",
        rule_description="dataclasses are banned per style guide. Use pydantic models instead",
        chunks=chunks,
    )


def test_prevent_namedtuple_usage() -> None:
    pattern = RegexPattern(r"\bnamedtuple\s*\(")
    chunks = check_regex_ratchet(_get_mngr_source_dir(), FileExtension(".py"), pattern, _THIS_FILE)

    assert len(chunks) <= snapshot(0), format_ratchet_failure_message(
        rule_name="namedtuple usage",
        rule_description="namedtuple is banned per style guide. Use pydantic models instead",
        chunks=chunks,
    )


def test_prevent_trailing_comments() -> None:
    # Allow trailing comments only for ty: ignore directives (needed for type checker)
    pattern = RegexPattern(r"[^\s#].*[ \t]#(?!\s*ty:\s*ignore\[)")
    chunks = check_regex_ratchet(_get_mngr_source_dir(), FileExtension(".py"), pattern, _THIS_FILE)

    assert len(chunks) <= snapshot(0), format_ratchet_failure_message(
        rule_name="trailing comments",
        rule_description="Comments should be on their own line, not trailing after code. Trailing comments make code harder to read",
        chunks=chunks,
    )


def test_prevent_relative_imports() -> None:
    pattern = RegexPattern(r"^from\s+\.", multiline=True)
    chunks = check_regex_ratchet(_get_mngr_source_dir(), FileExtension(".py"), pattern, _THIS_FILE)

    assert len(chunks) <= snapshot(0), format_ratchet_failure_message(
        rule_name="relative imports",
        rule_description="Always use absolute imports, never relative imports. Use 'from imbue.module' instead of 'from .'",
        chunks=chunks,
    )


def test_prevent_global_keyword() -> None:
    pattern = RegexPattern(r"^\s*global\s+\w+")
    chunks = check_regex_ratchet(_get_mngr_source_dir(), FileExtension(".py"), pattern, _THIS_FILE)

    assert len(chunks) <= snapshot(0), format_ratchet_failure_message(
        rule_name="global keyword usage",
        rule_description="Avoid using the 'global' keyword. Pass state explicitly through function parameters instead",
        chunks=chunks,
    )


def test_prevent_init_docstrings() -> None:
    pattern = RegexPattern(r'def __init__[^:]*:\s+"""', multiline=True)
    chunks = check_regex_ratchet(_get_mngr_source_dir(), FileExtension(".py"), pattern, _THIS_FILE)

    assert len(chunks) <= snapshot(0), format_ratchet_failure_message(
        rule_name="docstrings in __init__ methods",
        rule_description="Never create docstrings for __init__ methods. The class docstring should describe the class, not __init__",
        chunks=chunks,
    )


@pytest.mark.timeout(10)
def test_prevent_args_in_docstrings() -> None:
    # Use [\s\S] instead of . because . doesn't match newlines even with multiline=True
    pattern = RegexPattern(r'"""[\s\S]{0,500}Args:', multiline=True)
    chunks = check_regex_ratchet(_get_mngr_source_dir(), FileExtension(".py"), pattern, _THIS_FILE)

    assert len(chunks) <= snapshot(0), format_ratchet_failure_message(
        rule_name="Args: sections in docstrings",
        rule_description="Never include 'Args:' sections in docstrings. Use inline parameter comments if needed",
        chunks=chunks,
    )


@pytest.mark.timeout(10)
def test_prevent_returns_in_docstrings() -> None:
    # Use [\s\S] instead of . because . doesn't match newlines even with multiline=True
    pattern = RegexPattern(r'"""[\s\S]{0,500}Returns:', multiline=True)
    chunks = check_regex_ratchet(_get_mngr_source_dir(), FileExtension(".py"), pattern, _THIS_FILE)

    assert len(chunks) <= snapshot(0), format_ratchet_failure_message(
        rule_name="Returns: sections in docstrings",
        rule_description="Never include 'Returns:' sections in docstrings. Use inline return type comments if needed",
        chunks=chunks,
    )


def test_prevent_num_prefix() -> None:
    pattern = RegexPattern(r"\bnum_\w+|\bnumOf|\bnum[A-Z]")
    chunks = check_regex_ratchet(_get_mngr_source_dir(), FileExtension(".py"), pattern, _THIS_FILE)

    assert len(chunks) <= snapshot(2), format_ratchet_failure_message(
        rule_name="num prefix usage",
        rule_description="Avoid using 'num' prefix. Use 'count' or 'idx' instead (e.g., 'user_count' not 'num_users')",
        chunks=chunks,
    )


def test_prevent_builtin_exception_raises() -> None:
    pattern = RegexPattern(
        r"raise\s+(ValueError|KeyError|TypeError|AttributeError|IndexError|RuntimeError|OSError|IOError)\("
    )
    chunks = check_regex_ratchet(_get_mngr_source_dir(), FileExtension(".py"), pattern, _THIS_FILE)

    assert len(chunks) <= snapshot(0), format_ratchet_failure_message(
        rule_name="direct raising of built-in exceptions",
        rule_description="Never raise built-in exceptions directly. Create custom exception types that inherit from both the package base exception and the built-in",
        chunks=chunks,
    )


def test_prevent_yaml_usage() -> None:
    pattern = RegexPattern(r"yaml", multiline=True)
    chunks = check_regex_ratchet(_get_mngr_source_dir(), FileExtension(".py"), pattern, _THIS_FILE)

    assert len(chunks) <= snapshot(0), format_ratchet_failure_message(
        rule_name="yaml usage",
        rule_description="NEVER use YAML files. Use TOML for configuration instead",
        chunks=chunks,
    )


def test_no_type_errors() -> None:
    """Ensure the codebase has zero type errors.

    Runs the type checker (ty) and fails if any type errors are found.
    The full type checker output is included in the failure message for easy debugging.
    """
    project_root = Path(__file__).parent.parent.parent.parent
    result = subprocess.run(
        ["uv", "run", "ty", "check"],
        cwd=project_root,
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        error_lines = [
            line for line in result.stdout.splitlines() if line.startswith("error[") or "error:" in line.lower()
        ]
        error_count = len(error_lines)

        failure_message = [
            f"Type checker found {error_count} error(s):",
            "",
            "Full type checker output:",
            "=" * 80,
            result.stdout,
            "=" * 80,
        ]

        raise AssertionError("\n".join(failure_message))


def test_prevent_literal_with_multiple_options() -> None:
    pattern = RegexPattern(r"Literal\[.*,.*\]")
    chunks = check_regex_ratchet(_get_mngr_source_dir(), FileExtension(".py"), pattern, _THIS_FILE)

    assert len(chunks) <= snapshot(0), format_ratchet_failure_message(
        rule_name="Literal with multiple options",
        rule_description="Never use Literal with multiple string options. Create an UpperCaseStrEnum instead per the style guide",
        chunks=chunks,
    )


def test_no_ruff_errors() -> None:
    """Ensure the codebase has zero ruff linting errors.

    Runs the ruff linter and fails if any linting errors are found.
    The full ruff output is included in the failure message for easy debugging.
    """
    project_root = Path(__file__).parent.parent.parent.parent
    result = subprocess.run(
        ["uv", "run", "ruff", "check"],
        cwd=project_root,
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        failure_message = [
            "Ruff linter found errors:",
            "",
            "Full ruff output:",
            "=" * 80,
            result.stdout,
            "=" * 80,
        ]

        raise AssertionError("\n".join(failure_message))


def test_prevent_if_elif_without_else() -> None:
    """Prevent if/elif chains without else clauses.

    When an if statement has elif branches but no final else clause, it's easy to miss
    cases when conditions change. This test ensures all if/elif chains have an explicit
    else clause to handle the remaining cases.
    """
    chunks = find_if_elif_without_else(_get_mngr_source_dir(), _THIS_FILE)

    assert len(chunks) <= snapshot(0), format_ratchet_failure_message(
        rule_name="if/elif without else",
        rule_description="All if/elif chains must have an else clause to ensure all cases are handled explicitly",
        chunks=chunks,
    )


def test_prevent_import_datetime() -> None:
    pattern = RegexPattern(r"^import datetime$", multiline=True)
    chunks = check_regex_ratchet(_get_mngr_source_dir(), FileExtension(".py"), pattern, _THIS_FILE)

    assert len(chunks) <= snapshot(0), format_ratchet_failure_message(
        rule_name="import datetime",
        rule_description="Do not use 'import datetime'. Import specific items instead: 'from datetime import datetime, timedelta, etc.'",
        chunks=chunks,
    )


def test_prevent_inline_functions_in_non_test_code() -> None:
    chunks = find_inline_functions(_get_mngr_source_dir(), _THIS_FILE)

    assert len(chunks) <= snapshot(1), format_ratchet_failure_message(
        rule_name="inline functions in non-test code",
        rule_description="Functions should not be defined inside other functions in non-test code. Extract them as top-level functions or methods",
        chunks=chunks,
    )


def test_prevent_time_sleep() -> None:
    pattern = RegexPattern(r"\btime\.sleep\s*\(|\bfrom\s+time\s+import\s+sleep\b")
    chunks = check_regex_ratchet(_get_mngr_source_dir(), FileExtension(".py"), pattern, _THIS_FILE)

    assert len(chunks) <= snapshot(1), format_ratchet_failure_message(
        rule_name="time.sleep usage",
        rule_description="time.sleep is an antipattern. Instead, poll for the condition that you expect to be true. See wait_for",
        chunks=chunks,
    )


def test_prevent_bare_print() -> None:
    pattern = RegexPattern(r"^\s*print\s*\(", multiline=True)
    chunks = check_regex_ratchet(_get_mngr_source_dir(), FileExtension(".py"), pattern, _THIS_FILE)

    assert len(chunks) <= snapshot(0), format_ratchet_failure_message(
        rule_name="bare print statements",
        rule_description="Do not use bare print statements. Use logger.info(), logger.debug(), logger.warning(), etc instead",
        chunks=chunks,
    )


def test_prevent_importing_underscore_prefixed_names_in_non_test_code() -> None:
    chunks = find_underscore_imports(_get_mngr_source_dir(), _THIS_FILE)

    assert len(chunks) <= snapshot(0), format_ratchet_failure_message(
        rule_name="importing underscore-prefixed names in non-test code",
        rule_description="Do not import underscore-prefixed functions/classes/constants in non-test code. These are private and should not be used outside their defining module",
        chunks=chunks,
    )


def test_prevent_init_methods_in_non_exception_classes() -> None:
    chunks = find_init_methods_in_non_exception_classes(_get_mngr_source_dir(), _THIS_FILE)

    assert len(chunks) <= snapshot(3), format_ratchet_failure_message(
        rule_name="__init__ methods in non-Exception/Error classes",
        rule_description="Do not define __init__ methods in non-Exception/Error classes. Use Pydantic models instead, which handle initialization automatically",
        chunks=chunks,
    )


def test_prevent_click_echo() -> None:
    pattern = RegexPattern(r"\bclick\.echo\b|\bfrom\s+click\s+import\s+.*\becho\b")
    chunks = check_regex_ratchet(_get_mngr_source_dir(), FileExtension(".py"), pattern, _THIS_FILE)

    assert len(chunks) <= snapshot(0), format_ratchet_failure_message(
        rule_name="click.echo usage",
        rule_description="Do not use click.echo. Use logger.info() instead for consistent logging",
        chunks=chunks,
    )


def test_prevent_bare_generic_types() -> None:
    pattern = RegexPattern(r":\s*(list|dict|tuple|set|List|Dict|Tuple|Set|Mapping|Sequence)\s*($|[,\)\]])")
    chunks = check_regex_ratchet(_get_mngr_source_dir(), FileExtension(".py"), pattern, _THIS_FILE)

    assert len(chunks) <= snapshot(0), format_ratchet_failure_message(
        rule_name="bare generic types",
        rule_description="Generic types must specify their type parameters. Use 'list[str]' not 'list', 'dict[str, int]' not 'dict', etc.",
        chunks=chunks,
    )


def test_prevent_typing_builtin_imports() -> None:
    pattern = RegexPattern(r"\bfrom\s+typing\s+import\s+.*\b(Dict|List|Set|Tuple)\b")
    chunks = check_regex_ratchet(_get_mngr_source_dir(), FileExtension(".py"), pattern, _THIS_FILE)

    assert len(chunks) <= snapshot(0), format_ratchet_failure_message(
        rule_name="typing module imports for builtin types",
        rule_description="Do not import Dict, List, Set, or Tuple from typing. Use lowercase builtin types (dict, list, set, tuple) instead",
        chunks=chunks,
    )


def test_prevent_fstring_logging() -> None:
    pattern = RegexPattern(r"logger\.(trace|debug|info|warning|error|exception)\(f")
    chunks = check_regex_ratchet(_get_mngr_source_dir(), FileExtension(".py"), pattern, _THIS_FILE)

    assert len(chunks) <= snapshot(0), format_ratchet_failure_message(
        rule_name="f-string logging",
        rule_description="Do not use f-strings with loguru. Use loguru-style placeholder syntax instead: logger.info('message {}', var) instead of logger.info(f'message {var}')",
        chunks=chunks,
    )


def test_prevent_functools_partial() -> None:
    pattern = RegexPattern(r"\bfrom\s+functools\s+import\s+.*\bpartial\b|\bfunctools\.partial\b")
    chunks = check_regex_ratchet(_get_mngr_source_dir(), FileExtension(".py"), pattern, _THIS_FILE)

    assert len(chunks) <= snapshot(1), format_ratchet_failure_message(
        rule_name="functools.partial usage",
        rule_description="functools.partial is banned. It leads to confusing code and makes debugging difficult. Use explicit wrapper functions or lambdas instead",
        chunks=chunks,
    )


def test_prevent_code_in_init_files() -> None:
    """Ensure __init__.py files contain no code (except pluggy hookimpl at the root).

    The root __init__.py is allowed to contain the pluggy hookimpl marker.
    All other __init__.py files must be empty.
    """
    source_dir = _get_mngr_source_dir()
    root_init = source_dir / "__init__.py"

    # Find all __init__.py files
    init_files = list(source_dir.rglob("__init__.py"))

    violations: list[str] = []
    for init_file in init_files:
        content = init_file.read_text().strip()

        if init_file == root_init:
            # Root __init__.py is allowed to have pluggy hookimpl marker only
            allowed_lines = {"import pluggy", 'hookimpl = pluggy.HookimplMarker("mngr")'}
            actual_lines = {line.strip() for line in content.splitlines() if line.strip()}
            if actual_lines - allowed_lines:
                disallowed = actual_lines - allowed_lines
                violations.append(f"{init_file}: contains disallowed code: {disallowed}")
        else:
            # All other __init__.py files must be empty
            if content:
                violations.append(f"{init_file}: should be empty but contains: {content[:100]}...")

    assert len(violations) <= snapshot(0), (
        "Code found in __init__.py files (should be empty per style guide):\n"
        + "\n".join(f"  - {v}" for v in violations)
    )


def test_prevent_model_copy() -> None:
    """Prevent direct usage of .model_copy().

    Use model_copy_update instead:

        obj.model_copy_update(
            to_update(obj.field_ref().field_name, new_value),
        )

    model_copy_update wraps model_copy with type-safe field references.
    See style guide 'Type-safe model_copy_update' section for details.
    """
    pattern = RegexPattern(r"\.model_copy\(")
    chunks = check_regex_ratchet(_get_mngr_source_dir(), FileExtension(".py"), pattern, _THIS_FILE)

    assert len(chunks) <= snapshot(0), format_ratchet_failure_message(
        rule_name=".model_copy() usage",
        rule_description=(
            "Do not use .model_copy() directly. "
            "Use model_copy_update instead: obj.model_copy_update(to_update(obj.field_ref().field, value)). "
            "See style guide 'Type-safe model_copy_update' section."
        ),
        chunks=chunks,
    )


def test_prevent_cast_usage() -> None:
    """Prevent usage of cast() from typing in non-test code.

    cast() bypasses the type checker and should be avoided. If the type checker
    cannot infer the correct type, prefer using type: ignore comments with a
    specific error code only if there is really no other way to satisfy the
    type checker. Consider restructuring the code to avoid the need for cast().
    """
    chunks = find_cast_usages(_get_mngr_source_dir(), _THIS_FILE)

    assert len(chunks) <= snapshot(13), format_ratchet_failure_message(
        rule_name="cast() usages",
        rule_description=(
            "Do not use cast() from typing. It bypasses the type checker and makes code less safe. "
            "If you need to override the type checker, use a '# ty: ignore[specific-error]' comment instead, "
            "but only if there is really no other way. Consider restructuring your code to avoid the need for type overrides."
        ),
        chunks=chunks,
    )


def test_prevent_assert_isinstance_usage() -> None:
    """Prevent usage of 'assert isinstance(...)' in non-test code.

    'assert isinstance()' checks are often a sign of improper type handling. Instead,
    use match statements with exhaustive case handling to ensure all possible types
    are handled explicitly. Use 'case _ as unreachable: assert_never(unreachable)'
    to catch any unhandled cases at compile time.
    """
    chunks = find_assert_isinstance_usages(_get_mngr_source_dir(), _THIS_FILE)

    assert len(chunks) <= snapshot(2), format_ratchet_failure_message(
        rule_name="assert isinstance() usages",
        rule_description=(
            "Do not use 'assert isinstance()'. Use match statements with exhaustive case handling instead. "
            "End your match with 'case _ as unreachable: assert_never(unreachable)' to ensure all cases are "
            "handled and catch new variants at compile time. See style guide for examples."
        ),
        chunks=chunks,
    )


def test_prevent_direct_subprocess_usage() -> None:
    """Prevent direct usage of subprocess and os process-spawning functions.

    All subprocess execution should go through ConcurrencyGroup's run_process_to_completion
    to ensure proper process lifecycle management and cleanup. The only exceptions are
    interactive_subprocess.py (for terminal-interactive processes that bypass ConcurrencyGroup
    by design), and os.execvp in connect.py (which replaces the current process rather than
    spawning a child).

    Test files are excluded from this check.
    """
    pattern = RegexPattern(
        r"\bfrom\s+subprocess\s+import\b(Popen|run|call|check_call|check_output|getoutput|getstatusoutput)"
        r"|\bsubprocess\.(Popen|run|call|check_call|check_output|getoutput|getstatusoutput)\b"
        r"|\bos\.(exec\w+|spawn\w+|fork\w*|system|popen)\b"
        r"|\bfrom\s+os\s+import\b.*\b(exec\w+|spawn\w+|fork\w*|system|popen)\b",
    )
    all_chunks = check_regex_ratchet(_get_mngr_source_dir(), FileExtension(".py"), pattern, _THIS_FILE)
    chunks = tuple(c for c in all_chunks if not _is_test_file(c.file_path))

    assert len(chunks) <= snapshot(41), format_ratchet_failure_message(
        rule_name="direct subprocess/os.exec usage",
        rule_description=(
            "Do not use subprocess.Popen, subprocess.run, subprocess.call, subprocess.check_call, "
            "subprocess.check_output, os.exec*, os.spawn*, os.fork*, os.system, or os.popen directly. "
            "Instead, use run_process_to_completion from ConcurrencyGroup and ensure a ConcurrencyGroup "
            "is passed down to the call site. This ensures all spawned processes get cleaned up properly. "
            "See libs/concurrency_group/ for details."
        ),
        chunks=chunks,
    )


def test_prevent_unittest_mock_imports() -> None:
    """Prevent importing from unittest.mock.

    unittest.mock (Mock, MagicMock, patch, create_autospec, etc.) makes tests brittle
    and disconnected from real behavior. Instead, create concrete mock implementations
    of interfaces in mock_*_test.py files. See the style guide for details.
    """
    pattern = RegexPattern(r"from unittest\.mock import|from unittest import mock")
    chunks = check_regex_ratchet(_get_mngr_source_dir(), FileExtension(".py"), pattern, _THIS_FILE)

    assert len(chunks) <= snapshot(3), format_ratchet_failure_message(
        rule_name="unittest.mock imports",
        rule_description=(
            "Do not import from unittest.mock. Mock, MagicMock, patch, create_autospec, etc. make tests "
            "brittle and disconnected from real behavior. Instead, create concrete mock implementations "
            "of interfaces in mock_*_test.py files. See the style guide Testing section for details."
        ),
        chunks=chunks,
    )


def test_prevent_monkeypatch_setattr() -> None:
    """Prevent usage of monkeypatch.setattr to replace attributes/functions at runtime.

    monkeypatch.setattr makes tests brittle by replacing real behavior with fakes at
    the attribute level. Instead, use dependency injection and concrete mock implementations
    of interfaces. Note that monkeypatch.setenv, monkeypatch.delenv, and monkeypatch.chdir
    are fine -- only setattr is problematic.
    """
    pattern = RegexPattern(r"monkeypatch\.setattr")
    chunks = check_regex_ratchet(_get_mngr_source_dir(), FileExtension(".py"), pattern, _THIS_FILE)

    assert len(chunks) <= snapshot(30), format_ratchet_failure_message(
        rule_name="monkeypatch.setattr usages",
        rule_description=(
            "Do not use monkeypatch.setattr to replace attributes or functions at runtime. "
            "Use dependency injection and concrete mock implementations of interfaces instead. "
            "Note: monkeypatch.setenv, monkeypatch.delenv, and monkeypatch.chdir are fine."
        ),
        chunks=chunks,
    )
