import ast
from pathlib import Path

import deal

from imbue.imbue_common.ratchet_testing.core import FileExtension
from imbue.imbue_common.ratchet_testing.core import LineNumber
from imbue.imbue_common.ratchet_testing.core import RatchetMatchChunk
from imbue.imbue_common.ratchet_testing.core import _get_chunk_commit_date
from imbue.imbue_common.ratchet_testing.core import _get_non_ignored_files_with_extension
from imbue.imbue_common.ratchet_testing.core import _parse_file_ast


def find_if_elif_without_else(
    source_dir: Path,
    excluded_file: Path | None = None,
) -> tuple[RatchetMatchChunk, ...]:
    """Find all if/elif chains without else clauses using AST analysis."""
    file_paths = _get_non_ignored_files_with_extension(source_dir, FileExtension(".py"), excluded_file)
    chunks: list[RatchetMatchChunk] = []

    for file_path in file_paths:
        tree = _parse_file_ast(file_path)
        if tree is None:
            continue

        visited_if_nodes: set[int] = set()

        for node in ast.walk(tree):
            if isinstance(node, ast.If):
                if id(node) not in visited_if_nodes and _has_elif_without_else(node):
                    _mark_if_chain_as_visited(node, visited_if_nodes)

                    start_line = LineNumber(node.lineno)
                    end_line = LineNumber(_get_if_chain_end_line(node))

                    commit_date = _get_chunk_commit_date(file_path, start_line, end_line)

                    chunk = RatchetMatchChunk(
                        file_path=file_path,
                        matched_content=f"if/elif chain at line {start_line}",
                        start_line=start_line,
                        end_line=end_line,
                        last_modified_date=commit_date,
                    )
                    chunks.append(chunk)

    sorted_chunks = sorted(chunks, key=lambda c: c.last_modified_date, reverse=True)
    return tuple(sorted_chunks)


def _mark_if_chain_as_visited(if_node: ast.If, visited: set[int]) -> None:
    """Mark all If nodes in an if/elif chain as visited."""
    visited.add(id(if_node))
    current = if_node
    while current.orelse:
        first_in_orelse = current.orelse[0]
        if isinstance(first_in_orelse, ast.If):
            visited.add(id(first_in_orelse))
            current = first_in_orelse
        else:
            break


@deal.has()
def _has_elif_without_else(if_node: ast.If) -> bool:
    """Check if an If node has elif but no else clause."""
    if not if_node.orelse:
        return False

    first_orelse = if_node.orelse[0]

    if isinstance(first_orelse, ast.If):
        current = if_node
        while current.orelse:
            first_in_orelse = current.orelse[0]
            if isinstance(first_in_orelse, ast.If):
                current = first_in_orelse
            else:
                return False
        return True

    return False


@deal.has()
def _get_if_chain_end_line(if_node: ast.If) -> int:
    """Get the last line number of an if/elif chain."""
    current = if_node
    while current.orelse:
        first_in_orelse = current.orelse[0]
        if isinstance(first_in_orelse, ast.If):
            current = first_in_orelse
        else:
            break

    if hasattr(current, "end_lineno") and current.end_lineno is not None:
        return current.end_lineno

    return current.lineno


@deal.has()
def _is_test_file(file_path: Path) -> bool:
    """Check if a file is a test file."""
    return file_path.name.endswith("_test.py") or file_path.name.startswith("test_")


def _is_exception_or_error_class(
    class_name: str,
    class_bases: dict[str, list[str]],
    visited: set[str] | None = None,
) -> bool:
    """Check if a class is or inherits from an Exception or Error class.

    Recursively checks the inheritance chain within the same file.
    """
    if visited is None:
        visited = set()

    # Avoid infinite recursion
    if class_name in visited:
        return False
    visited.add(class_name)

    # Check if the class name itself ends with Exception or Error
    if class_name.endswith("Exception") or class_name.endswith("Error"):
        return True

    # Recursively check base classes
    if class_name in class_bases:
        for base in class_bases[class_name]:
            if _is_exception_or_error_class(base, class_bases, visited):
                return True

    return False


def find_init_methods_in_non_exception_classes(
    source_dir: Path,
    excluded_file: Path | None = None,
) -> tuple[RatchetMatchChunk, ...]:
    """Find __init__ method definitions in non-Exception/Error classes.

    Most classes should use Pydantic models which don't need __init__ methods.
    Only Exception/Error classes should define __init__ since they can't use Pydantic.
    """
    file_paths = _get_non_ignored_files_with_extension(source_dir, FileExtension(".py"), excluded_file)
    chunks: list[RatchetMatchChunk] = []

    for file_path in file_paths:
        if _is_test_file(file_path):
            continue

        tree = _parse_file_ast(file_path)
        if tree is None:
            continue

        # Build a map of class names to their base classes
        class_bases: dict[str, list[str]] = {}
        class_nodes: dict[str, ast.ClassDef] = {}

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                bases = []
                for base in node.bases:
                    if isinstance(base, ast.Name):
                        bases.append(base.id)
                    elif isinstance(base, ast.Attribute):
                        # Handle cases like module.ClassName
                        bases.append(base.attr)
                class_bases[node.name] = bases
                class_nodes[node.name] = node

        # Check each class for __init__ methods
        for class_name, class_node in class_nodes.items():
            # Check if this class has an __init__ method
            for item in class_node.body:
                if isinstance(item, ast.FunctionDef) and item.name == "__init__":
                    # Found an __init__ method
                    # Check if this class is an Exception/Error class
                    if not _is_exception_or_error_class(class_name, class_bases):
                        start_line = LineNumber(item.lineno)
                        end_line = LineNumber(item.end_lineno if item.end_lineno else item.lineno)

                        commit_date = _get_chunk_commit_date(file_path, start_line, end_line)

                        chunk = RatchetMatchChunk(
                            file_path=file_path,
                            matched_content=f"__init__ method in non-Exception/Error class '{class_name}'",
                            start_line=start_line,
                            end_line=end_line,
                            last_modified_date=commit_date,
                        )
                        chunks.append(chunk)

    sorted_chunks = sorted(chunks, key=lambda c: c.last_modified_date, reverse=True)
    return tuple(sorted_chunks)


@deal.has()
def _has_functools_wraps_decorator(func_node: ast.FunctionDef) -> bool:
    """Check if a function is decorated with @functools.wraps or @wraps.

    This is a standard pattern for creating decorators and should not be flagged
    as an inline function.
    """
    for decorator in func_node.decorator_list:
        # Check for @functools.wraps(...) or @wraps(...)
        if isinstance(decorator, ast.Call):
            func = decorator.func
            # Handle @wraps(...)
            if isinstance(func, ast.Name) and func.id == "wraps":
                return True
            # Handle @functools.wraps(...)
            if isinstance(func, ast.Attribute):
                if func.attr == "wraps" and isinstance(func.value, ast.Name) and func.value.id == "functools":
                    return True

    return False


def find_inline_functions(
    source_dir: Path,
    excluded_file: Path | None = None,
) -> tuple[RatchetMatchChunk, ...]:
    """Find functions defined inside other functions using AST analysis, excluding test files.

    Excludes decorator wrapper functions that use @functools.wraps, as these are
    a standard pattern for implementing decorators.
    """
    file_paths = _get_non_ignored_files_with_extension(source_dir, FileExtension(".py"), excluded_file)
    chunks: list[RatchetMatchChunk] = []

    for file_path in file_paths:
        if _is_test_file(file_path):
            continue

        tree = _parse_file_ast(file_path)
        if tree is None:
            continue

        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                for inner_node in ast.walk(node):
                    if inner_node is not node and isinstance(inner_node, ast.FunctionDef):
                        # Skip decorator wrapper functions that use @functools.wraps
                        if _has_functools_wraps_decorator(inner_node):
                            continue

                        start_line = LineNumber(inner_node.lineno)
                        end_line = LineNumber(inner_node.end_lineno if inner_node.end_lineno else inner_node.lineno)

                        commit_date = _get_chunk_commit_date(file_path, start_line, end_line)

                        chunk = RatchetMatchChunk(
                            file_path=file_path,
                            matched_content=f"inline function '{inner_node.name}' at line {start_line}",
                            start_line=start_line,
                            end_line=end_line,
                            last_modified_date=commit_date,
                        )
                        chunks.append(chunk)

    sorted_chunks = sorted(chunks, key=lambda c: c.last_modified_date, reverse=True)
    return tuple(sorted_chunks)


def find_underscore_imports(
    source_dir: Path,
    excluded_file: Path | None = None,
) -> tuple[RatchetMatchChunk, ...]:
    """Find imports of underscore-prefixed names using AST analysis, excluding test files."""
    file_paths = _get_non_ignored_files_with_extension(source_dir, FileExtension(".py"), excluded_file)
    chunks: list[RatchetMatchChunk] = []

    for file_path in file_paths:
        if _is_test_file(file_path):
            continue

        tree = _parse_file_ast(file_path)
        if tree is None:
            continue

        for node in ast.walk(tree):
            if isinstance(node, (ast.ImportFrom, ast.Import)):
                underscore_names: list[str] = []

                if isinstance(node, ast.ImportFrom):
                    if node.names:
                        for alias in node.names:
                            if alias.name.startswith("_"):
                                underscore_names.append(alias.name)

                elif isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name.startswith("_"):
                            underscore_names.append(alias.name)

                if underscore_names:
                    start_line = LineNumber(node.lineno)
                    end_line = LineNumber(node.end_lineno if node.end_lineno else node.lineno)

                    commit_date = _get_chunk_commit_date(file_path, start_line, end_line)

                    chunk = RatchetMatchChunk(
                        file_path=file_path,
                        matched_content=f"import of underscore-prefixed name(s): {', '.join(underscore_names)}",
                        start_line=start_line,
                        end_line=end_line,
                        last_modified_date=commit_date,
                    )
                    chunks.append(chunk)

    sorted_chunks = sorted(chunks, key=lambda c: c.last_modified_date, reverse=True)
    return tuple(sorted_chunks)


def find_cast_usages(
    source_dir: Path,
    excluded_file: Path | None = None,
) -> tuple[RatchetMatchChunk, ...]:
    """Find usages of cast() from typing in non-test files using AST analysis.

    This function finds all calls to cast() in Python files, excluding test files.
    cast() usage should be avoided in favor of type: ignore comments when there's
    no other way to satisfy the type checker.
    """
    file_paths = _get_non_ignored_files_with_extension(source_dir, FileExtension(".py"), excluded_file)
    chunks: list[RatchetMatchChunk] = []

    for file_path in file_paths:
        if _is_test_file(file_path):
            continue

        tree = _parse_file_ast(file_path)
        if tree is None:
            continue

        # Check if 'cast' is imported from typing
        has_cast_import = False
        cast_alias = "cast"
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                if node.module == "typing":
                    for alias in node.names:
                        if alias.name == "cast":
                            has_cast_import = True
                            cast_alias = alias.asname if alias.asname else "cast"
                            break

        if not has_cast_import:
            continue

        # Find all calls to cast()
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name) and node.func.id == cast_alias:
                    start_line = LineNumber(node.lineno)
                    end_line = LineNumber(node.end_lineno if node.end_lineno else node.lineno)

                    commit_date = _get_chunk_commit_date(file_path, start_line, end_line)

                    chunk = RatchetMatchChunk(
                        file_path=file_path,
                        matched_content=f"cast() usage at line {start_line}",
                        start_line=start_line,
                        end_line=end_line,
                        last_modified_date=commit_date,
                    )
                    chunks.append(chunk)

    sorted_chunks = sorted(chunks, key=lambda c: c.last_modified_date, reverse=True)
    return tuple(sorted_chunks)


def find_assert_isinstance_usages(
    source_dir: Path,
    excluded_file: Path | None = None,
) -> tuple[RatchetMatchChunk, ...]:
    """Find usages of 'assert isinstance(...)' in non-test files using AST analysis.

    This function finds all assert statements containing isinstance() calls in Python
    files, excluding test files. 'assert isinstance()' usage should be replaced with
    match constructs that exhaustively handle all cases using
    'case _ as unreachable: assert_never(unreachable)'.
    """
    file_paths = _get_non_ignored_files_with_extension(source_dir, FileExtension(".py"), excluded_file)
    chunks: list[RatchetMatchChunk] = []

    for file_path in file_paths:
        if _is_test_file(file_path):
            continue

        tree = _parse_file_ast(file_path)
        if tree is None:
            continue

        # Find all 'assert isinstance(...)' statements
        for node in ast.walk(tree):
            if isinstance(node, ast.Assert):
                # Check if the test is an isinstance() call
                if isinstance(node.test, ast.Call):
                    if isinstance(node.test.func, ast.Name) and node.test.func.id == "isinstance":
                        start_line = LineNumber(node.lineno)
                        end_line = LineNumber(node.end_lineno if node.end_lineno else node.lineno)

                        commit_date = _get_chunk_commit_date(file_path, start_line, end_line)

                        chunk = RatchetMatchChunk(
                            file_path=file_path,
                            matched_content=f"assert isinstance() at line {start_line}",
                            start_line=start_line,
                            end_line=end_line,
                            last_modified_date=commit_date,
                        )
                        chunks.append(chunk)

    sorted_chunks = sorted(chunks, key=lambda c: c.last_modified_date, reverse=True)
    return tuple(sorted_chunks)
