from imbue.mngr import hookimpl
from imbue.mngr.config.plugin_registry import register_plugin_config
from imbue.mngr.interfaces.agent import AgentInterface
from imbue.mngr.interfaces.host import OnlineHostInterface
from imbue.mngr.plugins.activity_tracking.data_types import ActivityTrackingConfig
from imbue.mngr.plugins.activity_tracking.data_types import PLUGIN_NAME

register_plugin_config(PLUGIN_NAME, ActivityTrackingConfig)


@hookimpl
def on_agent_created(agent: AgentInterface, host: OnlineHostInterface) -> None:
    """Store activity tracking config in agent plugin data for use by nginx.

    The actual script injection happens at the nginx layer. This hook stores
    the configuration so that the port_forwarding plugin can include the
    appropriate sub_filter directives when generating nginx config.
    """
    plugin_configs = agent.mngr_ctx.config.plugins
    config = plugin_configs.get(PLUGIN_NAME)
    if config is not None and not config.enabled:
        return

    debounce_ms = int(ActivityTrackingConfig().debounce_ms)
    if isinstance(config, ActivityTrackingConfig):
        debounce_ms = int(config.debounce_ms)

    agent.set_plugin_data(PLUGIN_NAME, {"debounce_ms": debounce_ms})
