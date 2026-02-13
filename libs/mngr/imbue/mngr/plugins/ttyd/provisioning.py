from pathlib import Path

from loguru import logger

from imbue.imbue_common.logging import log_span
from imbue.mngr.interfaces.agent import AgentInterface
from imbue.mngr.interfaces.host import OnlineHostInterface
from imbue.mngr.primitives import AgentId


def _compute_agent_state_dir(host: OnlineHostInterface, agent_id: AgentId) -> Path:
    """Compute the agent's state directory on the host."""
    return host.host_dir / "agents" / str(agent_id)


def install_ttyd_on_host(host: OnlineHostInterface) -> None:
    """Install ttyd on the remote host if not already present."""
    check_result = host.execute_command("command -v ttyd", timeout_seconds=5.0)
    if check_result.success:
        logger.debug("ttyd already installed on host {}", host.get_name())
        return

    with log_span("Installing ttyd on host {}", host.get_name()):
        install_cmd = (
            "curl -fsSL https://github.com/tsl0922/ttyd/releases/latest/download/ttyd.x86_64"
            " -o /usr/local/bin/ttyd && chmod +x /usr/local/bin/ttyd"
        )
        result = host.execute_command(install_cmd, user="root", timeout_seconds=120.0)
        if not result.success:
            logger.warning("Failed to install ttyd on host {}: {}", host.get_name(), result.stderr)


def start_ttyd_for_agent(
    host: OnlineHostInterface,
    agent: AgentInterface,
    ttyd_port: int,
    token: str,
) -> None:
    """Start ttyd connected to the agent's tmux session and register it with forward-service."""
    session_name = f"{agent.mngr_ctx.config.prefix}{agent.name}"
    agent_state_dir = _compute_agent_state_dir(host, agent.id)

    with log_span("Starting ttyd for agent {} on port {}", agent.name, ttyd_port):
        # Start ttyd in the background, connecting to the agent's tmux session.
        # The --credential flag uses ":<token>" format (empty username, token as password).
        start_cmd = (
            f"nohup ttyd --port {ttyd_port}"
            f" --credential :{token}"
            f" --writable"
            f" tmux attach-session -t '{session_name}'"
            f" > /dev/null 2>&1 &"
        )
        result = host.execute_command(start_cmd, timeout_seconds=10.0)
        if not result.success:
            logger.warning("Failed to start ttyd for agent {}: {}", agent.name, result.stderr)
            return

    with log_span("Registering terminal URL for agent {}", agent.name):
        # Call forward-service to register the ttyd port and write the URL
        forward_cmd = f"forward-service add --name terminal --port {ttyd_port}"
        env = {
            "MNGR_AGENT_STATE_DIR": str(agent_state_dir),
            "MNGR_AGENT_NAME": str(agent.name),
            "MNGR_HOST_NAME": str(host.get_name()),
        }
        result = host.execute_command(forward_cmd, env=env, timeout_seconds=10.0)
        if not result.success:
            logger.warning(
                "Failed to register terminal URL for agent {}: {}",
                agent.name,
                result.stderr,
            )


def stop_ttyd_for_agent(
    host: OnlineHostInterface,
    agent: AgentInterface,
    ttyd_port: int,
) -> None:
    """Stop the ttyd process for an agent and deregister from forward-service."""
    agent_state_dir = _compute_agent_state_dir(host, agent.id)

    # Kill the ttyd process on that port
    kill_cmd = f"pkill -f 'ttyd --port {ttyd_port}' || true"
    host.execute_command(kill_cmd, timeout_seconds=5.0)

    # Deregister from forward-service
    forward_cmd = "forward-service remove --name terminal"
    env = {
        "MNGR_AGENT_STATE_DIR": str(agent_state_dir),
        "MNGR_AGENT_NAME": str(agent.name),
        "MNGR_HOST_NAME": str(host.get_name()),
    }
    host.execute_command(forward_cmd, env=env, timeout_seconds=10.0)
