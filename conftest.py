"""Root conftest for the monorepo.

Common pytest hooks (test locking, timing limits, output file redirection) are
provided by the shared module imbue.imbue_common.conftest_hooks. Each project's
conftest.py calls register_conftest_hooks(globals()) to inject them. The shared
module ensures hooks are only registered once even when multiple conftest.py files
are discovered (e.g., when running from the monorepo root).
"""

from imbue.imbue_common.conftest_hooks import register_conftest_hooks
from imbue.mng.register_guards import register_mng_guards
from imbue.mng.utils.logging import suppress_warnings

# Suppress some pointless warnings from other library's loggers
suppress_warnings()

# Register mng-specific resource guards (SDK + binary), then the common conftest hooks
register_mng_guards()
register_conftest_hooks(globals())
