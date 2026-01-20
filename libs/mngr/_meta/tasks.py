# FIXME: this command:
#    uv run pytest -n 0 libs/mngr/imbue/mngr/agents/agent_registry_test.py
#  causes a warning:
#    CoverageWarning: Module imbue.mngr was previously imported, but not measured (module-not-measured); see https://coverage.readthedocs.io/en/7.13.1/messages.html#warning-module-not-measured self.warn(msg, slug="module-not-measured")
#  This particular warning should be suppressed
