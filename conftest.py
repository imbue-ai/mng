"""Root conftest for the monorepo.

Common pytest hooks (test locking, timing limits, output file redirection) are
provided by the shared module imbue.imbue_common.conftest_hooks. Each project's
conftest.py calls register_conftest_hooks(globals()) to inject them. The shared
module ensures hooks are only registered once even when multiple conftest.py files
are discovered (e.g., when running from the monorepo root).
"""

import os

import pytest

from imbue.imbue_common.conftest_hooks import register_conftest_hooks
from imbue.mng.utils.logging import suppress_warnings

# Suppress some pointless warnings from other library's loggers
suppress_warnings()

# Register the common conftest hooks (locking, timing, output file redirection)
register_conftest_hooks(globals())


@pytest.fixture(autouse=True)
def set_junit_classname_to_filepath(request, record_xml_attribute):
    """Set JUnit XML classname to match the file-based test ID from monorepo root."""
    fspath = str(request.node.fspath)

    # Find the monorepo root by looking for libs/ or apps/ or scripts/ directories
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
