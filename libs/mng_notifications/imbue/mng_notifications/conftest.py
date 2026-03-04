"""Test fixtures for mng-notifications.

Uses shared plugin test fixtures from mng for common setup (plugin manager,
environment isolation, etc.).
"""

from imbue.mng.utils.plugin_testing import register_plugin_test_fixtures

register_plugin_test_fixtures(globals())
