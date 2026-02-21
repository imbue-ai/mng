# Re-export fixtures from fixtures.py so pytest discovers them scoped to this directory.
# pytest only auto-discovers conftest.py, not fixtures.py. We keep fixture definitions
# in fixtures.py for discoverability (agents can glob for **/fixtures.py), and re-export
# them here to preserve directory scoping. pytest_plugins would make them global, which
# we don't want for subdirectory-specific fixtures.
from imbue.mng.cli.fixtures import default_connect_cli_opts as default_connect_cli_opts
from imbue.mng.cli.fixtures import default_create_cli_opts as default_create_cli_opts
from imbue.mng.cli.fixtures import intercepted_execvp_calls as intercepted_execvp_calls
