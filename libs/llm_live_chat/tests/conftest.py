import pathlib
import sys

# Must be set before any llm imports to prevent all entry-point plugins
# from being loaded, matching the behavior of the main test suite.
sys._called_from_test = True  # type: ignore[attr-defined]

import pytest  # noqa: E402

try:
    # These fixtures come from the llm source repo's test suite.
    # They are only available when running tests from inside the llm source checkout
    # (e.g. ~/project/llm/) with this plugin installed in editable mode.
    from tests.conftest import async_mock_model  # noqa: F401
    from tests.conftest import embed_demo  # noqa: F401
    from tests.conftest import env_setup  # noqa: F401
    from tests.conftest import logs_db  # noqa: F401
    from tests.conftest import mock_model  # noqa: F401
    from tests.conftest import register_echo_model  # noqa: F401
    from tests.conftest import register_embed_demo_model  # noqa: F401
    from tests.conftest import user_path  # noqa: F401

    _HAS_LLM_TEST_FIXTURES = True
except ImportError:
    _HAS_LLM_TEST_FIXTURES = False


def pytest_collection_modifyitems(config, items):
    if not _HAS_LLM_TEST_FIXTURES:
        skip = pytest.mark.skip(reason="llm test fixtures not available (run from llm source checkout)")
        this_dir = str(pathlib.Path(__file__).parent)
        for item in items:
            if str(item.fspath).startswith(this_dir):
                item.add_marker(skip)


if _HAS_LLM_TEST_FIXTURES:
    import llm.cli  # noqa: E402
    from llm.plugins import pm  # noqa: E402

    import imbue.llm_live_chat.plugin as llm_live_chat_plugin  # noqa: E402

    @pytest.fixture(autouse=True)
    def register_live_chat_plugin():
        if not pm.is_registered(llm_live_chat_plugin):
            pm.register(llm_live_chat_plugin, name="undo-llm-live-chat")
        # The register_commands hook already fired during llm.cli import,
        # so we must call it manually for our plugin.
        if "live-chat" not in llm.cli.cli.commands:
            llm_live_chat_plugin.register_commands(llm.cli.cli)
        yield
