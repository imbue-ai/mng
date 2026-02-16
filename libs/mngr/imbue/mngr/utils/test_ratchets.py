import re
import subprocess
from pathlib import Path

import pytest
from inline_snapshot import snapshot

from imbue.imbue_common.ratchet_testing.common_ratchets import PREVENT_ARGS_IN_DOCSTRINGS
from imbue.imbue_common.ratchet_testing.common_ratchets import PREVENT_ASSERT_ISINSTANCE
from imbue.imbue_common.ratchet_testing.common_ratchets import PREVENT_ASYNCIO_IMPORT
from imbue.imbue_common.ratchet_testing.common_ratchets import PREVENT_BARE_EXCEPT
from imbue.imbue_common.ratchet_testing.common_ratchets import PREVENT_BARE_GENERIC_TYPES
from imbue.imbue_common.ratchet_testing.common_ratchets import PREVENT_BARE_PRINT
from imbue.imbue_common.ratchet_testing.common_ratchets import PREVENT_BASE_EXCEPTION_CATCH
from imbue.imbue_common.ratchet_testing.common_ratchets import PREVENT_BROAD_EXCEPTION_CATCH
from imbue.imbue_common.ratchet_testing.common_ratchets import PREVENT_BUILTIN_EXCEPTION_RAISES
from imbue.imbue_common.ratchet_testing.common_ratchets import PREVENT_CAST_USAGE
from imbue.imbue_common.ratchet_testing.common_ratchets import PREVENT_CLICK_ECHO
from imbue.imbue_common.ratchet_testing.common_ratchets import PREVENT_DATACLASSES_IMPORT
from imbue.imbue_common.ratchet_testing.common_ratchets import PREVENT_DIRECT_SUBPROCESS
from imbue.imbue_common.ratchet_testing.common_ratchets import PREVENT_EVAL
from imbue.imbue_common.ratchet_testing.common_ratchets import PREVENT_EXEC
from imbue.imbue_common.ratchet_testing.common_ratchets import PREVENT_FSTRING_LOGGING
from imbue.imbue_common.ratchet_testing.common_ratchets import PREVENT_FUNCTOOLS_PARTIAL
from imbue.imbue_common.ratchet_testing.common_ratchets import PREVENT_GLOBAL_KEYWORD
from imbue.imbue_common.ratchet_testing.common_ratchets import PREVENT_IF_ELIF_WITHOUT_ELSE
from imbue.imbue_common.ratchet_testing.common_ratchets import PREVENT_IMPORTLIB_IMPORT_MODULE
from imbue.imbue_common.ratchet_testing.common_ratchets import PREVENT_IMPORT_DATETIME
from imbue.imbue_common.ratchet_testing.common_ratchets import PREVENT_INIT_DOCSTRINGS
from imbue.imbue_common.ratchet_testing.common_ratchets import PREVENT_INIT_IN_NON_EXCEPTION_CLASSES
from imbue.imbue_common.ratchet_testing.common_ratchets import PREVENT_INLINE_FUNCTIONS
from imbue.imbue_common.ratchet_testing.common_ratchets import PREVENT_INLINE_IMPORTS
from imbue.imbue_common.ratchet_testing.common_ratchets import PREVENT_LITERAL_MULTIPLE_OPTIONS
from imbue.imbue_common.ratchet_testing.common_ratchets import PREVENT_MODEL_COPY
from imbue.imbue_common.ratchet_testing.common_ratchets import PREVENT_MONKEYPATCH_SETATTR
from imbue.imbue_common.ratchet_testing.common_ratchets import PREVENT_NAMEDTUPLE
from imbue.imbue_common.ratchet_testing.common_ratchets import PREVENT_NUM_PREFIX
from imbue.imbue_common.ratchet_testing.common_ratchets import PREVENT_PANDAS_IMPORT
from imbue.imbue_common.ratchet_testing.common_ratchets import PREVENT_PYTEST_MARK_INTEGRATION
from imbue.imbue_common.ratchet_testing.common_ratchets import PREVENT_RELATIVE_IMPORTS
from imbue.imbue_common.ratchet_testing.common_ratchets import PREVENT_RETURNS_IN_DOCSTRINGS
from imbue.imbue_common.ratchet_testing.common_ratchets import PREVENT_SHORT_UUID_IDS
from imbue.imbue_common.ratchet_testing.common_ratchets import PREVENT_TEST_CONTAINER_CLASSES
from imbue.imbue_common.ratchet_testing.common_ratchets import PREVENT_TIME_SLEEP
from imbue.imbue_common.ratchet_testing.common_ratchets import PREVENT_TODOS
from imbue.imbue_common.ratchet_testing.common_ratchets import PREVENT_TRAILING_COMMENTS
from imbue.imbue_common.ratchet_testing.common_ratchets import PREVENT_TYPING_BUILTIN_IMPORTS
from imbue.imbue_common.ratchet_testing.common_ratchets import PREVENT_UNDERSCORE_IMPORTS
from imbue.imbue_common.ratchet_testing.common_ratchets import PREVENT_UNITTEST_MOCK_IMPORTS
from imbue.imbue_common.ratchet_testing.common_ratchets import PREVENT_WHILE_TRUE
from imbue.imbue_common.ratchet_testing.common_ratchets import PREVENT_YAML_USAGE
from imbue.imbue_common.ratchet_testing.common_ratchets import check_ratchet_rule
from imbue.imbue_common.ratchet_testing.core import clear_ratchet_caches
from imbue.imbue_common.ratchet_testing.ratchets import TEST_FILE_PATTERNS
from imbue.imbue_common.ratchet_testing.ratchets import _is_test_file
from imbue.imbue_common.ratchet_testing.ratchets import find_assert_isinstance_usages
from imbue.imbue_common.ratchet_testing.ratchets import find_cast_usages
from imbue.imbue_common.ratchet_testing.ratchets import find_if_elif_without_else
from imbue.imbue_common.ratchet_testing.ratchets import find_init_methods_in_non_exception_classes
from imbue.imbue_common.ratchet_testing.ratchets import find_inline_functions
from imbue.imbue_common.ratchet_testing.ratchets import find_underscore_imports

# Exclude this test file from ratchet scans to prevent self-referential matches
_SELF_EXCLUSION: tuple[str, ...] = ("test_ratchets.py",)

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
    chunks = check_ratchet_rule(PREVENT_TODOS, _get_mngr_source_dir(), _SELF_EXCLUSION)
    assert len(chunks) <= snapshot(2), PREVENT_TODOS.format_failure(chunks)


def test_prevent_exec_usage() -> None:
    chunks = check_ratchet_rule(PREVENT_EXEC, _get_mngr_source_dir(), _SELF_EXCLUSION)
    assert len(chunks) <= snapshot(0), PREVENT_EXEC.format_failure(chunks)


def test_prevent_eval_usage() -> None:
    chunks = check_ratchet_rule(PREVENT_EVAL, _get_mngr_source_dir(), _SELF_EXCLUSION)
    assert len(chunks) <= snapshot(0), PREVENT_EVAL.format_failure(chunks)


def test_prevent_inline_imports() -> None:
    chunks = check_ratchet_rule(PREVENT_INLINE_IMPORTS, _get_mngr_source_dir(), _SELF_EXCLUSION)
    assert len(chunks) <= snapshot(2), PREVENT_INLINE_IMPORTS.format_failure(chunks)


def test_prevent_bare_except() -> None:
    chunks = check_ratchet_rule(PREVENT_BARE_EXCEPT, _get_mngr_source_dir(), _SELF_EXCLUSION)
    assert len(chunks) <= snapshot(0), PREVENT_BARE_EXCEPT.format_failure(chunks)


def test_prevent_broad_exception_catch() -> None:
    chunks = check_ratchet_rule(PREVENT_BROAD_EXCEPTION_CATCH, _get_mngr_source_dir(), _SELF_EXCLUSION)
    assert len(chunks) <= snapshot(0), PREVENT_BROAD_EXCEPTION_CATCH.format_failure(chunks)


def test_prevent_base_exception_catch() -> None:
    chunks = check_ratchet_rule(PREVENT_BASE_EXCEPTION_CATCH, _get_mngr_source_dir(), _SELF_EXCLUSION)
    assert len(chunks) <= snapshot(1), PREVENT_BASE_EXCEPTION_CATCH.format_failure(chunks)


def test_prevent_while_true() -> None:
    chunks = check_ratchet_rule(PREVENT_WHILE_TRUE, _get_mngr_source_dir(), _SELF_EXCLUSION)
    assert len(chunks) <= snapshot(0), PREVENT_WHILE_TRUE.format_failure(chunks)


def test_prevent_asyncio_import() -> None:
    chunks = check_ratchet_rule(PREVENT_ASYNCIO_IMPORT, _get_mngr_source_dir(), _SELF_EXCLUSION)
    assert len(chunks) <= snapshot(0), PREVENT_ASYNCIO_IMPORT.format_failure(chunks)


def test_prevent_pandas_import() -> None:
    chunks = check_ratchet_rule(PREVENT_PANDAS_IMPORT, _get_mngr_source_dir(), _SELF_EXCLUSION)
    assert len(chunks) <= snapshot(0), PREVENT_PANDAS_IMPORT.format_failure(chunks)


def test_prevent_dataclasses_import() -> None:
    chunks = check_ratchet_rule(PREVENT_DATACLASSES_IMPORT, _get_mngr_source_dir(), _SELF_EXCLUSION)
    assert len(chunks) <= snapshot(0), PREVENT_DATACLASSES_IMPORT.format_failure(chunks)


def test_prevent_namedtuple_usage() -> None:
    chunks = check_ratchet_rule(PREVENT_NAMEDTUPLE, _get_mngr_source_dir(), _SELF_EXCLUSION)
    assert len(chunks) <= snapshot(0), PREVENT_NAMEDTUPLE.format_failure(chunks)


def test_prevent_trailing_comments() -> None:
    chunks = check_ratchet_rule(PREVENT_TRAILING_COMMENTS, _get_mngr_source_dir(), _SELF_EXCLUSION)
    assert len(chunks) <= snapshot(0), PREVENT_TRAILING_COMMENTS.format_failure(chunks)


def test_prevent_relative_imports() -> None:
    chunks = check_ratchet_rule(PREVENT_RELATIVE_IMPORTS, _get_mngr_source_dir(), _SELF_EXCLUSION)
    assert len(chunks) <= snapshot(0), PREVENT_RELATIVE_IMPORTS.format_failure(chunks)


def test_prevent_global_keyword() -> None:
    chunks = check_ratchet_rule(PREVENT_GLOBAL_KEYWORD, _get_mngr_source_dir(), _SELF_EXCLUSION)
    assert len(chunks) <= snapshot(0), PREVENT_GLOBAL_KEYWORD.format_failure(chunks)


def test_prevent_init_docstrings() -> None:
    chunks = check_ratchet_rule(PREVENT_INIT_DOCSTRINGS, _get_mngr_source_dir(), _SELF_EXCLUSION)
    assert len(chunks) <= snapshot(0), PREVENT_INIT_DOCSTRINGS.format_failure(chunks)


@pytest.mark.timeout(10)
def test_prevent_args_in_docstrings() -> None:
    chunks = check_ratchet_rule(PREVENT_ARGS_IN_DOCSTRINGS, _get_mngr_source_dir(), _SELF_EXCLUSION)
    assert len(chunks) <= snapshot(0), PREVENT_ARGS_IN_DOCSTRINGS.format_failure(chunks)


@pytest.mark.timeout(10)
def test_prevent_returns_in_docstrings() -> None:
    chunks = check_ratchet_rule(PREVENT_RETURNS_IN_DOCSTRINGS, _get_mngr_source_dir(), _SELF_EXCLUSION)
    assert len(chunks) <= snapshot(0), PREVENT_RETURNS_IN_DOCSTRINGS.format_failure(chunks)


def test_prevent_num_prefix() -> None:
    chunks = check_ratchet_rule(PREVENT_NUM_PREFIX, _get_mngr_source_dir(), _SELF_EXCLUSION)
    assert len(chunks) <= snapshot(2), PREVENT_NUM_PREFIX.format_failure(chunks)


def test_prevent_builtin_exception_raises() -> None:
    chunks = check_ratchet_rule(PREVENT_BUILTIN_EXCEPTION_RAISES, _get_mngr_source_dir(), _SELF_EXCLUSION)
    assert len(chunks) <= snapshot(0), PREVENT_BUILTIN_EXCEPTION_RAISES.format_failure(chunks)


def test_prevent_yaml_usage() -> None:
    chunks = check_ratchet_rule(PREVENT_YAML_USAGE, _get_mngr_source_dir(), _SELF_EXCLUSION)
    assert len(chunks) <= snapshot(0), PREVENT_YAML_USAGE.format_failure(chunks)


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
    chunks = check_ratchet_rule(PREVENT_LITERAL_MULTIPLE_OPTIONS, _get_mngr_source_dir(), _SELF_EXCLUSION)
    assert len(chunks) <= snapshot(0), PREVENT_LITERAL_MULTIPLE_OPTIONS.format_failure(chunks)


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
    chunks = find_if_elif_without_else(_get_mngr_source_dir(), _SELF_EXCLUSION)
    assert len(chunks) <= snapshot(0), PREVENT_IF_ELIF_WITHOUT_ELSE.format_failure(chunks)


def test_prevent_import_datetime() -> None:
    chunks = check_ratchet_rule(PREVENT_IMPORT_DATETIME, _get_mngr_source_dir(), _SELF_EXCLUSION)
    assert len(chunks) <= snapshot(0), PREVENT_IMPORT_DATETIME.format_failure(chunks)


def test_prevent_inline_functions_in_non_test_code() -> None:
    chunks = find_inline_functions(_get_mngr_source_dir())
    assert len(chunks) <= snapshot(0), PREVENT_INLINE_FUNCTIONS.format_failure(chunks)


def test_prevent_time_sleep() -> None:
    chunks = check_ratchet_rule(PREVENT_TIME_SLEEP, _get_mngr_source_dir(), _SELF_EXCLUSION)
    assert len(chunks) <= snapshot(1), PREVENT_TIME_SLEEP.format_failure(chunks)


def test_prevent_bare_print() -> None:
    chunks = check_ratchet_rule(PREVENT_BARE_PRINT, _get_mngr_source_dir(), _SELF_EXCLUSION)
    assert len(chunks) <= snapshot(0), PREVENT_BARE_PRINT.format_failure(chunks)


def test_prevent_importing_underscore_prefixed_names_in_non_test_code() -> None:
    chunks = find_underscore_imports(_get_mngr_source_dir())
    assert len(chunks) <= snapshot(0), PREVENT_UNDERSCORE_IMPORTS.format_failure(chunks)


def test_prevent_init_methods_in_non_exception_classes() -> None:
    chunks = find_init_methods_in_non_exception_classes(_get_mngr_source_dir())
    assert len(chunks) <= snapshot(3), PREVENT_INIT_IN_NON_EXCEPTION_CLASSES.format_failure(chunks)


def test_prevent_click_echo() -> None:
    chunks = check_ratchet_rule(PREVENT_CLICK_ECHO, _get_mngr_source_dir(), _SELF_EXCLUSION)
    assert len(chunks) <= snapshot(0), PREVENT_CLICK_ECHO.format_failure(chunks)


def test_prevent_bare_generic_types() -> None:
    chunks = check_ratchet_rule(PREVENT_BARE_GENERIC_TYPES, _get_mngr_source_dir(), _SELF_EXCLUSION)
    assert len(chunks) <= snapshot(0), PREVENT_BARE_GENERIC_TYPES.format_failure(chunks)


def test_prevent_typing_builtin_imports() -> None:
    chunks = check_ratchet_rule(PREVENT_TYPING_BUILTIN_IMPORTS, _get_mngr_source_dir(), _SELF_EXCLUSION)
    assert len(chunks) <= snapshot(0), PREVENT_TYPING_BUILTIN_IMPORTS.format_failure(chunks)


def test_prevent_fstring_logging() -> None:
    chunks = check_ratchet_rule(PREVENT_FSTRING_LOGGING, _get_mngr_source_dir(), _SELF_EXCLUSION)
    assert len(chunks) <= snapshot(0), PREVENT_FSTRING_LOGGING.format_failure(chunks)


def test_prevent_functools_partial() -> None:
    chunks = check_ratchet_rule(PREVENT_FUNCTOOLS_PARTIAL, _get_mngr_source_dir(), _SELF_EXCLUSION)
    assert len(chunks) <= snapshot(0), PREVENT_FUNCTOOLS_PARTIAL.format_failure(chunks)


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
    chunks = check_ratchet_rule(PREVENT_MODEL_COPY, _get_mngr_source_dir(), _SELF_EXCLUSION)
    assert len(chunks) <= snapshot(0), PREVENT_MODEL_COPY.format_failure(chunks)


def test_prevent_cast_usage() -> None:
    chunks = find_cast_usages(_get_mngr_source_dir())
    assert len(chunks) <= snapshot(10), PREVENT_CAST_USAGE.format_failure(chunks)


def test_prevent_assert_isinstance_usage() -> None:
    chunks = find_assert_isinstance_usages(_get_mngr_source_dir())
    assert len(chunks) <= snapshot(0), PREVENT_ASSERT_ISINSTANCE.format_failure(chunks)


def test_prevent_direct_subprocess_usage() -> None:
    """Prevent direct usage of subprocess and os process-spawning functions.

    All subprocess execution should go through ConcurrencyGroup's run_process_to_completion
    to ensure proper process lifecycle management and cleanup. The only exceptions are
    interactive_subprocess.py (for terminal-interactive processes that bypass ConcurrencyGroup
    by design), and os.execvp in connect.py (which replaces the current process rather than
    spawning a child).

    Test files are excluded from this check.
    """
    chunks = check_ratchet_rule(PREVENT_DIRECT_SUBPROCESS, _get_mngr_source_dir(), TEST_FILE_PATTERNS)
    assert len(chunks) <= snapshot(45), PREVENT_DIRECT_SUBPROCESS.format_failure(chunks)


def test_prevent_unittest_mock_imports() -> None:
    chunks = check_ratchet_rule(PREVENT_UNITTEST_MOCK_IMPORTS, _get_mngr_source_dir(), _SELF_EXCLUSION)
    assert len(chunks) <= snapshot(3), PREVENT_UNITTEST_MOCK_IMPORTS.format_failure(chunks)


def test_prevent_monkeypatch_setattr() -> None:
    chunks = check_ratchet_rule(PREVENT_MONKEYPATCH_SETATTR, _get_mngr_source_dir(), _SELF_EXCLUSION)
    assert len(chunks) <= snapshot(25), PREVENT_MONKEYPATCH_SETATTR.format_failure(chunks)


def test_prevent_test_container_classes() -> None:
    all_chunks = check_ratchet_rule(PREVENT_TEST_CONTAINER_CLASSES, _get_mngr_source_dir(), _SELF_EXCLUSION)
    chunks = tuple(c for c in all_chunks if _is_test_file(c.file_path))
    assert len(chunks) <= snapshot(0), PREVENT_TEST_CONTAINER_CLASSES.format_failure(chunks)


def test_prevent_pytest_mark_integration() -> None:
    chunks = check_ratchet_rule(PREVENT_PYTEST_MARK_INTEGRATION, _get_mngr_source_dir(), _SELF_EXCLUSION)
    assert len(chunks) <= snapshot(0), PREVENT_PYTEST_MARK_INTEGRATION.format_failure(chunks)


def test_prevent_short_uuid_ids() -> None:
    chunks = check_ratchet_rule(PREVENT_SHORT_UUID_IDS, _get_mngr_source_dir(), _SELF_EXCLUSION)
    assert len(chunks) <= snapshot(2), PREVENT_SHORT_UUID_IDS.format_failure(chunks)


def test_prevent_bash_without_strict_mode() -> None:
    """Ensure all bash scripts use 'set -euo pipefail' for strict error handling.

    Without strict mode, bash scripts silently ignore errors, use unset variables,
    and mask failures in pipelines. Every bash script should include
    'set -euo pipefail' near the top.
    """
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=Path(__file__).parent,
        capture_output=True,
        text=True,
        check=True,
    )
    repo_root = Path(result.stdout.strip())

    ls_result = subprocess.run(
        ["git", "ls-files", "*.sh"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=True,
    )

    sh_files = [repo_root / line.strip() for line in ls_result.stdout.splitlines() if line.strip()]

    strict_mode_pattern = re.compile(r"set\s+-(?=[^ ]*e)(?=[^ ]*u)(?=[^ ]*o)[euo]+\s+pipefail")

    violations: list[str] = []
    for sh_file in sh_files:
        content = sh_file.read_text()
        if not strict_mode_pattern.search(content):
            violations.append(str(sh_file))

    assert len(violations) <= snapshot(0), "Bash scripts missing 'set -euo pipefail':\n" + "\n".join(
        f"  - {v}" for v in violations
    )


def test_prevent_importlib_import_module() -> None:
    chunks = check_ratchet_rule(PREVENT_IMPORTLIB_IMPORT_MODULE, _get_mngr_source_dir(), _SELF_EXCLUSION)
    assert len(chunks) <= snapshot(0), PREVENT_IMPORTLIB_IMPORT_MODULE.format_failure(chunks)
