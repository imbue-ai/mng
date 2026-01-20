from collections.abc import Sequence
from typing import Any

import celpy
import deal
from celpy.celparser import CELParseError
from celpy.evaluation import CELEvalError
from loguru import logger

from imbue.mngr.errors import MngrError


@deal.has()
def compile_cel_filters(
    include_filters: Sequence[str],
    exclude_filters: Sequence[str],
) -> tuple[list[Any], list[Any]]:
    """Compile CEL filter expressions into evaluable programs.

    Raises MngrError if any filter expression is invalid.
    """
    compiled_includes: list[Any] = []
    compiled_excludes: list[Any] = []

    env = celpy.Environment()

    for filter_expr in include_filters:
        try:
            ast = env.compile(filter_expr)
            prgm = env.program(ast)
            compiled_includes.append(prgm)
        except CELParseError as e:
            raise MngrError(f"Invalid include filter expression '{filter_expr}': {e}") from e

    for filter_expr in exclude_filters:
        try:
            ast = env.compile(filter_expr)
            prgm = env.program(ast)
            compiled_excludes.append(prgm)
        except CELParseError as e:
            raise MngrError(f"Invalid exclude filter expression '{filter_expr}': {e}") from e

    return compiled_includes, compiled_excludes


def apply_cel_filters_to_context(
    context: dict[str, Any],
    include_filters: Sequence[Any],
    exclude_filters: Sequence[Any],
    # Used in warning messages to identify what is being filtered
    error_context_description: str,
) -> bool:
    """Apply CEL filters to a context dictionary.

    Returns True if the context should be included (matches all include filters
    and doesn't match any exclude filters).
    """
    for prgm in include_filters:
        try:
            result = prgm.evaluate(context)
            if not result:
                return False
        except CELEvalError as e:
            logger.warning("Error evaluating include filter on {}: {}", error_context_description, e)
            return False

    for prgm in exclude_filters:
        try:
            result = prgm.evaluate(context)
            if result:
                return False
        except CELEvalError as e:
            logger.warning("Error evaluating exclude filter on {}: {}", error_context_description, e)
            continue

    return True
