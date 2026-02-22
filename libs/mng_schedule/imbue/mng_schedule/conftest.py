"""Test fixtures for mng-schedule.

Uses shared plugin test fixtures from mng to avoid duplicating common
fixture code across plugin libraries.
"""

from imbue.mng.utils.plugin_testing import register_plugin_test_fixtures

register_plugin_test_fixtures(globals())
