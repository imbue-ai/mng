import os
from pathlib import Path

from loguru import logger

from imbue.mngr.api.data_types import ConnectionOptions
from imbue.mngr.config.data_types import MngrContext
from imbue.mngr.errors import MngrError
from imbue.mngr.interfaces.agent import AgentInterface
from imbue.mngr.interfaces.host import HostInterface


def _build_ssh_activity_wrapper_script(session_name: str, host_dir: Path) -> str:
    """Build a shell script that tracks SSH activity while running tmux.

    The script:
    1. Creates the activity directory if needed
    2. Starts a background loop that writes JSON activity to activity/ssh
    3. Runs tmux attach (foreground, blocking)
    4. Kills the activity tracker when tmux exits

    The activity file contains JSON with:
    - time: milliseconds since Unix epoch (int)
    - ssh_pid: the PID of the SSH activity tracker process (for debugging)

    Note: The authoritative activity time is the file's mtime, not the JSON content.
    """
    activity_dir = host_dir / "activity"
    activity_file = activity_dir / "ssh"
    # Use single quotes around most things to avoid shell expansion issues,
    # but the paths need to be interpolated
    return (
        f"mkdir -p '{activity_dir}'; "
        f"(while true; do "
        f"TIME_MS=$(($(date +%s) * 1000)); "
        f'printf \'{{\\n  "time": %d,\\n  "ssh_pid": %d\\n}}\\n\' "$TIME_MS" "$$" > \'{activity_file}\'; '
        f"sleep 5; done) & "
        "MNGR_ACTIVITY_PID=$!; "
        f"tmux attach -t '{session_name}'; "
        "kill $MNGR_ACTIVITY_PID 2>/dev/null"
    )


def connect_to_agent(
    agent: AgentInterface,
    host: HostInterface,
    mngr_ctx: MngrContext,
    connection_opts: ConnectionOptions,
) -> None:
    """Connect to an agent by replacing the current process with tmux attach.

    For local agents, executes: tmux attach -t <session_name>
    For remote agents, executes: ssh <host> <activity_wrapper_script>

    The activity wrapper script tracks SSH activity by writing timestamps to the
    host's activity/ssh file while the SSH connection is open.

    This function does not return - it replaces the current process.
    """
    logger.info("Connecting to agent...")

    session_name = f"{mngr_ctx.config.prefix}{agent.name}"

    if host.is_local:
        os.execvp("tmux", ["tmux", "attach", "-t", session_name])
    else:
        pyinfra_host = host.connector.host
        ssh_host = pyinfra_host.name
        ssh_user = pyinfra_host.data.get("ssh_user")
        ssh_port = pyinfra_host.data.get("ssh_port")
        ssh_key = pyinfra_host.data.get("ssh_key")
        ssh_known_hosts_file = pyinfra_host.data.get("ssh_known_hosts_file")

        ssh_args = ["ssh"]

        if ssh_key:
            ssh_args.extend(["-i", str(ssh_key)])

        if ssh_port:
            ssh_args.extend(["-p", str(ssh_port)])

        # Use the known_hosts file if provided (for pre-trusted host keys)
        if ssh_known_hosts_file and ssh_known_hosts_file != "/dev/null":
            ssh_args.extend(["-o", f"UserKnownHostsFile={ssh_known_hosts_file}"])
            ssh_args.extend(["-o", "StrictHostKeyChecking=yes"])
        elif connection_opts.is_unknown_host_allowed:
            # Fall back to disabling host key checking if no known_hosts file
            ssh_args.extend(["-o", "StrictHostKeyChecking=no"])
            ssh_args.extend(["-o", "UserKnownHostsFile=/dev/null"])
        else:
            raise MngrError(
                "You must specify a known_hosts file to connect to this host securely. "
                "Alternatively, use --allow-unknown-host to bypass SSH host key verification."
            )

        if ssh_user:
            ssh_args.append(f"{ssh_user}@{ssh_host}")
        else:
            ssh_args.append(ssh_host)

        # Build wrapper script that tracks SSH activity while running tmux
        wrapper_script = _build_ssh_activity_wrapper_script(session_name, host.host_dir)
        ssh_args.extend(["-t", "bash", "-c", wrapper_script])

        os.execvp("ssh", ssh_args)
