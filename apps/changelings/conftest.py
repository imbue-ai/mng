"""Project-level conftest for changelings.

When running tests from apps/changelings/, this conftest provides the common pytest hooks
that would otherwise come from the monorepo root conftest.py (which is not discovered
when pytest runs from a subdirectory).

When running from the monorepo root, the root conftest.py registers the hooks first,
and this file's register_conftest_hooks() call is a no-op (guarded by a module-level flag).
"""

import os

import pytest

from imbue.imbue_common.conftest_hooks import register_conftest_hooks
from imbue.mng.utils.logging import suppress_warnings

suppress_warnings()
register_conftest_hooks(globals())


@pytest.fixture(autouse=True)
def set_junit_classname_to_filepath(request, record_xml_attribute):
    """Set JUnit XML classname to match the file-based test ID from monorepo root."""
    fspath = str(request.node.fspath)

    mng_root = None
    path_parts = fspath.split(os.sep)
    for i, part in enumerate(path_parts):
        if part in ("libs", "apps", "scripts") and i + 1 < len(path_parts):
            mng_root = os.sep.join(path_parts[:i])
            break

    if mng_root and fspath.startswith(mng_root):
        rel_path = os.path.relpath(fspath, mng_root)
    else:
        rel_path = request.node.nodeid.split("::")[0]

    classname = rel_path.replace(os.sep, ".").replace("/", ".").removesuffix(".py")
    record_xml_attribute("classname", classname)
