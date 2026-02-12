from imbue.imbue_common.pure import pure


@pure
def generate_forward_service_script(
    domain_suffix: str,
    vhost_port: int,
    frpc_config_dir: str,
) -> str:
    """Generate the forward-service shell script installed on remote hosts.

    This script is called by agents to register/unregister port forwards.
    It manages frpc proxy entries and writes URLs to the agent's status/urls/ directory.

    Required environment variables (set during agent provisioning):
      MNGR_AGENT_STATE_DIR - path to the agent's state directory
      MNGR_AGENT_NAME      - the agent's name
      MNGR_HOST_NAME        - the host's name
    """
    return f'''#!/usr/bin/env bash
set -euo pipefail

DOMAIN_SUFFIX="{domain_suffix}"
VHOST_PORT="{vhost_port}"
FRPC_CONFIG_DIR="{frpc_config_dir}"

usage() {{
    echo "Usage: forward-service <add|remove|list> [options]"
    echo ""
    echo "Commands:"
    echo "  add    --name <name> --port <port>   Forward a local port"
    echo "  remove --name <name>                 Remove a forward"
    echo "  list                                  List current forwards"
    exit 1
}}

require_env() {{
    local var_name="$1"
    if [ -z "${{!var_name:-}}" ]; then
        echo "Error: $var_name environment variable is not set" >&2
        exit 1
    fi
}}

sanitize_name() {{
    echo "$1" | tr '[:upper:]' '[:lower:]' | tr '_.' '-' | sed 's/-\\+/-/g; s/^-//; s/-$//'
}}

cmd_add() {{
    local name=""
    local port=""
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --name) name="$2"; shift 2 ;;
            --port) port="$2"; shift 2 ;;
            *) echo "Unknown option: $1" >&2; exit 1 ;;
        esac
    done
    if [ -z "$name" ] || [ -z "$port" ]; then
        echo "Error: --name and --port are required" >&2
        exit 1
    fi

    require_env MNGR_AGENT_STATE_DIR
    require_env MNGR_AGENT_NAME
    require_env MNGR_HOST_NAME

    local service_label
    service_label=$(sanitize_name "$name")
    local agent_label
    agent_label=$(sanitize_name "$MNGR_AGENT_NAME")
    local host_label
    host_label=$(sanitize_name "$MNGR_HOST_NAME")
    local subdomain="${{service_label}}.${{agent_label}}.${{host_label}}"
    local proxy_name="${{subdomain//./-}}"
    local custom_domain="${{subdomain}}.${{DOMAIN_SUFFIX}}"
    local url="http://${{custom_domain}}:${{VHOST_PORT}}"

    # Write frpc proxy config fragment
    local proxy_file="$FRPC_CONFIG_DIR/proxies/${{proxy_name}}.toml"
    mkdir -p "$FRPC_CONFIG_DIR/proxies"
    cat > "$proxy_file" <<PROXY_EOF
[[proxies]]
name = "$proxy_name"
type = "http"
localPort = $port
customDomains = ["$custom_domain"]
PROXY_EOF

    # Reload frpc to pick up new proxy
    if command -v frpc &>/dev/null; then
        frpc reload -c "$FRPC_CONFIG_DIR/frpc.toml" 2>/dev/null || true
    fi

    # Write the URL to the agent's status/urls directory
    local urls_dir="$MNGR_AGENT_STATE_DIR/status/urls"
    mkdir -p "$urls_dir"
    echo -n "$url" > "$urls_dir/$name"

    echo "$url"
}}

cmd_remove() {{
    local name=""
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --name) name="$2"; shift 2 ;;
            *) echo "Unknown option: $1" >&2; exit 1 ;;
        esac
    done
    if [ -z "$name" ]; then
        echo "Error: --name is required" >&2
        exit 1
    fi

    require_env MNGR_AGENT_STATE_DIR
    require_env MNGR_AGENT_NAME
    require_env MNGR_HOST_NAME

    local service_label
    service_label=$(sanitize_name "$name")
    local agent_label
    agent_label=$(sanitize_name "$MNGR_AGENT_NAME")
    local host_label
    host_label=$(sanitize_name "$MNGR_HOST_NAME")
    local subdomain="${{service_label}}.${{agent_label}}.${{host_label}}"
    local proxy_name="${{subdomain//./-}}"

    # Remove frpc proxy config fragment
    local proxy_file="$FRPC_CONFIG_DIR/proxies/${{proxy_name}}.toml"
    rm -f "$proxy_file"

    # Reload frpc
    if command -v frpc &>/dev/null; then
        frpc reload -c "$FRPC_CONFIG_DIR/frpc.toml" 2>/dev/null || true
    fi

    # Remove the URL from the agent's status/urls directory
    local urls_dir="$MNGR_AGENT_STATE_DIR/status/urls"
    rm -f "$urls_dir/$name"

    echo "Removed forward: $name"
}}

cmd_list() {{
    require_env MNGR_AGENT_STATE_DIR

    local urls_dir="$MNGR_AGENT_STATE_DIR/status/urls"
    if [ ! -d "$urls_dir" ]; then
        echo "No forwarded services."
        exit 0
    fi

    for url_file in "$urls_dir"/*; do
        [ -f "$url_file" ] || continue
        local name
        name=$(basename "$url_file")
        local url
        url=$(cat "$url_file")
        echo "$name -> $url"
    done
}}

if [ $# -lt 1 ]; then
    usage
fi

command="$1"
shift

case "$command" in
    add) cmd_add "$@" ;;
    remove) cmd_remove "$@" ;;
    list) cmd_list "$@" ;;
    *) echo "Unknown command: $command" >&2; usage ;;
esac
'''
