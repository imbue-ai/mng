import os
import subprocess
from pathlib import Path
from typing import Final

from loguru import logger

from imbue.mngr.api.data_types import ConnectionOptions
from imbue.mngr.config.data_types import MngrContext
from imbue.mngr.errors import MngrError
from imbue.mngr.interfaces.agent import AgentInterface
from imbue.mngr.interfaces.host import OnlineHostInterface

# Exit codes used by the remote SSH wrapper script to signal post-disconnect actions.
# These are checked by connect_to_agent after the SSH session ends to determine
# whether to destroy or stop the agent locally.
SIGNAL_EXIT_CODE_DESTROY: Final[int] = 10
SIGNAL_EXIT_CODE_STOP: Final[int] = 11


def _build_ssh_activity_wrapper_script(session_name: str, host_dir: Path) -> str:
    """Build a shell script that tracks SSH activity while running tmux.

    The script:
    1. Creates the activity directory if needed
    2. Starts a background loop that writes JSON activity to activity/ssh
    3. Runs tmux attach (foreground, blocking)
    4. Kills the activity tracker when tmux exits
    5. Checks for signal files (written by tmux Ctrl-q/Ctrl-t bindings) and
       exits with a specific code to tell the local mngr process what to do

    The activity file contains JSON with:
    - time: milliseconds since Unix epoch (int)
    - ssh_pid: the PID of the SSH activity tracker process (for debugging)

    Note: The authoritative activity time is the file's mtime, not the JSON content.
    """
    activity_dir = host_dir / "activity"
    activity_file = activity_dir / "ssh"
    signal_file = host_dir / "signals" / session_name
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
        "kill $MNGR_ACTIVITY_PID 2>/dev/null; "
        # Check for signal files written by tmux key bindings (Ctrl-q writes "destroy", Ctrl-t writes "stop")
        f"SIGNAL_FILE='{signal_file}'; "
        'if [ -f "$SIGNAL_FILE" ]; then '
        'ACTION=$(cat "$SIGNAL_FILE"); '
        'rm -f "$SIGNAL_FILE"; '
        f'if [ "$ACTION" = "destroy" ]; then exit {SIGNAL_EXIT_CODE_DESTROY}; '
        f'elif [ "$ACTION" = "stop" ]; then exit {SIGNAL_EXIT_CODE_STOP}; fi; '
        "fi"
    )


def _build_ssh_args(
    host: OnlineHostInterface,
    connection_opts: ConnectionOptions,
) -> list[str]:
    """Build the SSH command arguments for connecting to a remote host.

    Returns the list of arguments for the SSH command (not including the
    wrapper script or -t bash -c ... suffix).
    """
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

    return ssh_args


def connect_to_agent(
    agent: AgentInterface,
    host: OnlineHostInterface,
    mngr_ctx: MngrContext,
    connection_opts: ConnectionOptions,
) -> None:
    """Connect to an agent via tmux attach (local) or SSH + tmux attach (remote).

    For local agents, replaces the current process with: tmux attach -t <session_name>

    For remote agents, runs SSH interactively and then checks the exit code to
    determine if a post-disconnect action (destroy/stop) was requested via the
    tmux key bindings (Ctrl-q for destroy, Ctrl-t for stop). If so, replaces the
    current process with the appropriate mngr command to perform the action locally.

    For local agents, this function does not return (os.execvp replaces the process).
    For remote agents, this function returns after the SSH session ends unless a
    post-disconnect action is triggered (in which case os.execvp replaces the process).
    """
    logger.info("Connecting to agent...")

    session_name = f"{mngr_ctx.config.prefix}{agent.name}"

    if host.is_local:
        os.execvp("tmux", ["tmux", "attach", "-t", session_name])
    else:
        ssh_args = _build_ssh_args(host, connection_opts)

        # Build wrapper script that tracks SSH activity while running tmux
        wrapper_script = _build_ssh_activity_wrapper_script(session_name, host.host_dir)
        ssh_args.extend(["-t", "bash", "-c", wrapper_script])

        # Use subprocess.call instead of os.execvp so we can check the exit code
        # and run post-disconnect actions (destroy/stop) triggered by tmux key bindings
        exit_code = subprocess.call(ssh_args)

        if exit_code == SIGNAL_EXIT_CODE_DESTROY:
            logger.info("Destroying agent after disconnect: {}", agent.name)
            os.execvp("mngr", ["mngr", "destroy", "--session", session_name, "-f"])
        elif exit_code == SIGNAL_EXIT_CODE_STOP:
            logger.info("Stopping agent after disconnect: {}", agent.name)
            os.execvp("mngr", ["mngr", "stop", "--session", session_name])
        else:
            logger.debug("SSH session ended with exit code {} (no post-disconnect action)", exit_code)
