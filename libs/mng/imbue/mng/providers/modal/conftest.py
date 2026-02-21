# Re-export fixtures from fixtures.py so pytest discovers them scoped to this directory.
# pytest only auto-discovers conftest.py, not fixtures.py. We keep fixture definitions
# in fixtures.py for discoverability (agents can glob for **/fixtures.py), and re-export
# them here to preserve directory scoping. pytest_plugins would make them global, which
# we don't want for subdirectory-specific fixtures.
from imbue.mng.providers.modal.fixtures import initial_snapshot_provider as initial_snapshot_provider
from imbue.mng.providers.modal.fixtures import modal_mng_ctx as modal_mng_ctx
from imbue.mng.providers.modal.fixtures import persistent_modal_provider as persistent_modal_provider
from imbue.mng.providers.modal.fixtures import real_modal_provider as real_modal_provider
