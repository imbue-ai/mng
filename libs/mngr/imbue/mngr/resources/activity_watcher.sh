#!/bin/bash
# Activity watcher script for mngr hosts.
# This script monitors activity files and calls shutdown.sh when the host becomes idle.
#
# Usage: activity_watcher.sh <host_data_dir>
#
# The script reads idle_mode and max_idle_seconds from <host_data_dir>/data.json
# and monitors the relevant activity files based on the idle mode.
#
# Activity sources per idle mode (from docs/concepts/idle_detection.md):
#   IO (default): USER, AGENT, SSH, CREATE, START, BOOT
#   USER: USER, SSH, CREATE, START, BOOT
#   AGENT: AGENT, SSH, CREATE, START, BOOT
#   SSH: SSH, CREATE, START, BOOT
#   CREATE: CREATE
#   BOOT: BOOT
#   START: START, BOOT
#   RUN: CREATE, START, BOOT, PROCESS
#   DISABLED: (never idle - script exits immediately)
#
# Host-level activity files: <host_data_dir>/activity/<source_name>
#   - boot, user, ssh
# Agent-level activity files: <host_data_dir>/agents/<agent_id>/activity/<source_name>
#   - create, start, agent, process
#
# The script checks activity every 60 seconds. When all relevant activity files
# have mtimes older than (current_time - idle_timeout_seconds), the script calls
# <host_data_dir>/commands/shutdown.sh.

set -e

HOST_DATA_DIR="$1"

if [ -z "$HOST_DATA_DIR" ]; then
    echo "Usage: activity_watcher.sh <host_data_dir>" >&2
    exit 1
fi

DATA_JSON="$HOST_DATA_DIR/data.json"
SHUTDOWN_SCRIPT="$HOST_DATA_DIR/commands/shutdown.sh"
CHECK_INTERVAL=60

# Get the mtime of a file as Unix timestamp, or 0 if file doesn't exist
get_mtime() {
    local file="$1"
    if [ -f "$file" ]; then
        # Try Linux stat first, then macOS stat
        stat -c %Y "$file" 2>/dev/null || stat -f %m "$file" 2>/dev/null || echo 0
    else
        echo 0
    fi
}

# Get activity sources for a given idle mode
# Returns space-separated list of source names (uppercase to match ActivitySource enum)
get_activity_sources() {
    local idle_mode="$1"
    case "$idle_mode" in
        IO)
            echo "USER AGENT SSH CREATE START BOOT"
            ;;
        USER)
            echo "USER SSH CREATE START BOOT"
            ;;
        AGENT)
            echo "AGENT SSH CREATE START BOOT"
            ;;
        SSH)
            echo "SSH CREATE START BOOT"
            ;;
        CREATE)
            echo "CREATE"
            ;;
        BOOT)
            echo "BOOT"
            ;;
        START)
            echo "START BOOT"
            ;;
        RUN)
            echo "CREATE START BOOT PROCESS"
            ;;
        DISABLED)
            echo ""
            ;;
        *)
            # Default to AGENT mode if unknown
            echo "AGENT SSH CREATE START BOOT"
            ;;
    esac
}

# Check if a source is host-level (vs agent-level)
# Host-level: boot, user, ssh
# Agent-level: create, start, agent, process
is_host_level_source() {
    local source="$1"
    case "$source" in
        BOOT|USER|SSH)
            return 0  # true
            ;;
        *)
            return 1  # false
            ;;
    esac
}

# Get the maximum mtime across all relevant activity files
get_max_activity_mtime() {
    local idle_mode="$1"
    local max_mtime=0
    local sources
    sources=$(get_activity_sources "$idle_mode")

    # If no sources (DISABLED mode), return 0
    if [ -z "$sources" ]; then
        echo 0
        return
    fi

    # Check host-level activity files
    for source in $sources; do
        if is_host_level_source "$source"; then
            local activity_file="$HOST_DATA_DIR/activity/$source"
            local mtime
            mtime=$(get_mtime "$activity_file")
            if [ "$mtime" -gt "$max_mtime" ]; then
                max_mtime=$mtime
            fi
        fi
    done

    # Check agent-level activity files
    local agents_dir="$HOST_DATA_DIR/agents"
    if [ -d "$agents_dir" ]; then
        for agent_dir in "$agents_dir"/*; do
            if [ -d "$agent_dir" ]; then
                for source in $sources; do
                    if ! is_host_level_source "$source"; then
                        local activity_file="$agent_dir/activity/$source"
                        local mtime
                        mtime=$(get_mtime "$activity_file")
                        if [ "$mtime" -gt "$max_mtime" ]; then
                            max_mtime=$mtime
                        fi
                    fi
                done
            fi
        done
    fi

    echo "$max_mtime"
}

# Read configuration from data.json
read_config() {
    if [ ! -f "$DATA_JSON" ]; then
        echo "AGENT 3600"
        return
    fi

    # Parse idle_mode and max_idle_seconds from JSON
    # Using basic shell parsing since jq may not be available
    local idle_mode
    local timeout

    # Try to extract idle_mode - look for "idle_mode": "VALUE"
    idle_mode=$(grep -o '"idle_mode"[[:space:]]*:[[:space:]]*"[^"]*"' "$DATA_JSON" 2>/dev/null | head -1 | sed 's/.*"idle_mode"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/')
    if [ -z "$idle_mode" ]; then
        idle_mode="AGENT"
    fi

    # Try to extract max_idle_seconds - look for "max_idle_seconds": NUMBER
    timeout=$(grep -o '"max_idle_seconds"[[:space:]]*:[[:space:]]*[0-9]*' "$DATA_JSON" 2>/dev/null | head -1 | sed 's/.*"max_idle_seconds"[[:space:]]*:[[:space:]]*\([0-9]*\).*/\1/')
    if [ -z "$timeout" ]; then
        timeout=3600
    fi

    echo "$idle_mode $timeout"
}

main() {
    echo "Activity watcher starting for $HOST_DATA_DIR"

    while true; do
        # Read current configuration (may change at runtime)
        local config
        config=$(read_config)
        local idle_mode
        local idle_timeout_seconds
        idle_mode=$(echo "$config" | cut -d' ' -f1)
        idle_timeout_seconds=$(echo "$config" | cut -d' ' -f2)

        # DISABLED mode means never idle - just sleep and continue
        if [ "$idle_mode" = "DISABLED" ]; then
            sleep "$CHECK_INTERVAL"
            continue
        fi

        # Get the maximum activity time
        local max_mtime
        max_mtime=$(get_max_activity_mtime "$idle_mode")

        # If no activity files found (max_mtime=0), wait for activity to be recorded
        if [ "$max_mtime" -eq 0 ]; then
            sleep "$CHECK_INTERVAL"
            continue
        fi

        # Calculate idle deadline
        local current_time
        current_time=$(date +%s)
        local idle_deadline=$((max_mtime + idle_timeout_seconds))

        # Check if we're past the idle deadline
        if [ "$current_time" -ge "$idle_deadline" ]; then
            echo "Host is idle (last activity: $max_mtime, deadline: $idle_deadline, now: $current_time)"

            # Call shutdown script if it exists
            if [ -x "$SHUTDOWN_SCRIPT" ]; then
                echo "Calling shutdown script: $SHUTDOWN_SCRIPT"
                "$SHUTDOWN_SCRIPT"
                # Exit after calling shutdown (the script should handle the actual shutdown)
                exit 0
            else
                echo "Shutdown script not found or not executable: $SHUTDOWN_SCRIPT"
                # Continue monitoring in case the script appears later
            fi
        fi

        sleep "$CHECK_INTERVAL"
    done
}

main
