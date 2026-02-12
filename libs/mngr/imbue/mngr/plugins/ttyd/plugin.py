from imbue.mngr import hookimpl
from imbue.mngr.config.plugin_registry import register_plugin_config
from imbue.mngr.interfaces.agent import AgentInterface
from imbue.mngr.interfaces.host import OnlineHostInterface
from imbue.mngr.plugins.ttyd.data_types import PLUGIN_NAME
from imbue.mngr.plugins.ttyd.data_types import TtydConfig
from imbue.mngr.plugins.ttyd.data_types import generate_ttyd_token
from imbue.mngr.plugins.ttyd.provisioning import install_ttyd_on_host
from imbue.mngr.plugins.ttyd.provisioning import start_ttyd_for_agent
from imbue.mngr.plugins.ttyd.provisioning import stop_ttyd_for_agent
from imbue.mngr.primitives import PluginName

register_plugin_config(PLUGIN_NAME, TtydConfig)

# Plugin data keys
_DATA_KEY_PORT: str = "ttyd_port"
_DATA_KEY_TOKEN: str = "ttyd_token"


def _get_ttyd_config(agent: AgentInterface) -> TtydConfig | None:
    """Extract the ttyd config from the agent's MngrContext, returning None if disabled."""
    plugin_configs = agent.mngr_ctx.config.plugins
    config = plugin_configs.get(PluginName(PLUGIN_NAME))
    if config is None:
        return TtydConfig()
    if not config.enabled:
        return None
    if isinstance(config, TtydConfig):
        return config
    return TtydConfig()


def _allocate_port(agent: AgentInterface, config: TtydConfig) -> int:
    """Allocate a ttyd port for an agent using a hash-based offset from the base port."""
    offset = hash(str(agent.id)) % 1000
    return int(config.base_port) + offset


@hookimpl
def on_agent_created(agent: AgentInterface, host: OnlineHostInterface) -> None:
    """Install ttyd and start a web terminal for the agent."""
    config = _get_ttyd_config(agent)
    if config is None:
        return

    # Install ttyd on the host if needed
    install_ttyd_on_host(host)

    # Allocate port and generate token
    port = _allocate_port(agent, config)
    token = generate_ttyd_token()

    # Store port and token in agent plugin data for later cleanup
    agent.set_plugin_data(PLUGIN_NAME, {_DATA_KEY_PORT: port, _DATA_KEY_TOKEN: token})

    # Start ttyd and register with forward-service
    start_ttyd_for_agent(host=host, agent=agent, ttyd_port=port, token=token)


@hookimpl
def on_agent_destroyed(agent: AgentInterface, host: OnlineHostInterface) -> None:
    """Stop ttyd when an agent is destroyed."""
    plugin_data = agent.get_plugin_data(PLUGIN_NAME)
    port = plugin_data.get(_DATA_KEY_PORT)
    if port is None:
        return

    stop_ttyd_for_agent(host=host, agent=agent, ttyd_port=int(port))
