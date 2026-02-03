#!/bin/bash
# Activity watcher script for mngr hosts.
# This script monitors activity files and calls shutdown.sh when the host becomes idle.
#
# Usage: activity_watcher.sh <host_data_dir>
#
# The script reads from <host_data_dir>/data.json:
#   - activity_sources: array of activity source names (e.g., ["BOOT", "USER", "AGENT"])
#   - idle_timeout_seconds: the idle timeout in seconds
#   - max_host_age: (optional) maximum host age in seconds from boot
#
# Activity sources are converted to file patterns:
#   - Host-level sources (BOOT, USER, SSH): <host_data_dir>/activity/<source>
#   - Agent-level sources (CREATE, START, AGENT, PROCESS): <host_data_dir>/agents/*/activity/<source>
#
# When the maximum mtime of all matched files + idle_timeout < current_time,
# the script calls <host_data_dir>/commands/shutdown.sh.
#
# Additionally, if max_host_age exists in data.json, the script will trigger shutdown when:
#   current_time > boot_activity_file_mtime + max_host_age_seconds
# This ensures the host shuts down cleanly before external timeouts (e.g., Modal sandbox timeout).

set -e

HOST_DATA_DIR="$1"

if [ -z "$HOST_DATA_DIR" ]; then
    echo "Usage: activity_watcher.sh <host_data_dir>" >&2
    exit 1
fi

DATA_JSON_PATH="$HOST_DATA_DIR/data.json"
BOOT_ACTIVITY_PATH="$HOST_DATA_DIR/activity/boot"
SHUTDOWN_SCRIPT="$HOST_DATA_DIR/commands/shutdown.sh"
CHECK_INTERVAL=60

# Host-level activity sources (as opposed to agent-level)
HOST_LEVEL_SOURCES="boot user ssh"

# Get the mtime of a file as Unix timestamp, or empty string if file doesn't exist
get_mtime() {
    local file="$1"
    if [ -f "$file" ]; then
        # Try Linux stat first, then macOS stat
        stat -c %Y "$file" 2>/dev/null || stat -f %m "$file" 2>/dev/null || echo ""
    fi
}

# Check if a source is host-level (vs agent-level)
is_host_level_source() {
    local source="$1"
    local source_lower
    source_lower=$(echo "$source" | tr '[:upper:]' '[:lower:]')
    for hs in $HOST_LEVEL_SOURCES; do
        if [ "$source_lower" = "$hs" ]; then
            return 0
        fi
    done
    return 1
}

# Read activity_sources from data.json and return as space-separated lowercase list
get_activity_sources() {
    if [ ! -f "$DATA_JSON_PATH" ]; then
        echo ""
        return
    fi
    # Extract activity_sources array, convert to lowercase, output as space-separated
    jq -r '.activity_sources // [] | .[] | ascii_downcase' "$DATA_JSON_PATH" 2>/dev/null | tr '\n' ' '
}

# Read idle_timeout_seconds from data.json
get_idle_timeout_seconds() {
    if [ ! -f "$DATA_JSON_PATH" ]; then
        echo ""
        return
    fi
    jq -r '.idle_timeout_seconds // empty' "$DATA_JSON_PATH" 2>/dev/null
}

# Read max_host_age from data.json (optional field)
get_max_host_age() {
    if [ ! -f "$DATA_JSON_PATH" ]; then
        echo ""
        return
    fi
    jq -r '.max_host_age // empty' "$DATA_JSON_PATH" 2>/dev/null
}

# Check if the host has exceeded its maximum age (hard timeout)
# Returns 0 (true) if the host should be shut down due to age, 1 (false) otherwise
check_max_host_age() {
    local max_host_age_seconds
    max_host_age_seconds=$(get_max_host_age)

    # If no max_host_age, no hard timeout applies
    if [ -z "$max_host_age_seconds" ]; then
        return 1
    fi

    # Get boot activity file mtime
    local boot_mtime
    boot_mtime=$(get_mtime "$BOOT_ACTIVITY_PATH")
    if [ -z "$boot_mtime" ]; then
        # No boot activity file yet, can't determine age
        return 1
    fi

    # Check if we've exceeded max age
    local current_time
    current_time=$(date +%s)
    local max_age_deadline=$((boot_mtime + max_host_age_seconds))

    if [ "$current_time" -ge "$max_age_deadline" ]; then
        echo "Host has exceeded maximum age (boot: $boot_mtime, max_age: $max_host_age_seconds, deadline: $max_age_deadline, now: $current_time)"
        return 0
    fi

    return 1
}

# Get the maximum mtime across all activity files for the configured sources
get_max_activity_mtime() {
    local max_mtime=0
    local activity_sources
    activity_sources=$(get_activity_sources)

    # If no activity sources configured (DISABLED mode), return 0
    if [ -z "$activity_sources" ]; then
        echo "0"
        return
    fi

    for source in $activity_sources; do
        if is_host_level_source "$source"; then
            # Host-level source: single file at <host_data_dir>/activity/<source>
            local file="$HOST_DATA_DIR/activity/$source"
            if [ -f "$file" ]; then
                local mtime
                mtime=$(get_mtime "$file")
                if [ -n "$mtime" ] && [ "$mtime" -gt "$max_mtime" ]; then
                    max_mtime=$mtime
                fi
            fi
        else
            # Agent-level source: glob pattern <host_data_dir>/agents/*/activity/<source>
            # shellcheck disable=SC2086
            for file in "$HOST_DATA_DIR"/agents/*/activity/$source; do
                if [ -f "$file" ]; then
                    local mtime
                    mtime=$(get_mtime "$file")
                    if [ -n "$mtime" ] && [ "$mtime" -gt "$max_mtime" ]; then
                        max_mtime=$mtime
                    fi
                fi
            done
        fi
    done

    echo "$max_mtime"
}

main() {
    echo "Activity watcher starting for $HOST_DATA_DIR"
    echo "Data JSON path: $DATA_JSON_PATH"
    echo "Boot activity path: $BOOT_ACTIVITY_PATH"
    echo "Shutdown script path: $SHUTDOWN_SCRIPT"
    echo "Check interval: $CHECK_INTERVAL seconds"

    while true; do
        echo "--- Activity watcher check at $(date) ---"

        # Log current state for debugging
        if [ -f "$DATA_JSON_PATH" ]; then
            echo "data.json exists"
            local max_host_age_val
            max_host_age_val=$(get_max_host_age)
            echo "max_host_age from data.json: $max_host_age_val"
        else
            echo "data.json NOT found at $DATA_JSON_PATH"
        fi

        if [ -f "$BOOT_ACTIVITY_PATH" ]; then
            local boot_mtime
            boot_mtime=$(get_mtime "$BOOT_ACTIVITY_PATH")
            echo "boot activity file exists, mtime: $boot_mtime"
        else
            echo "boot activity file NOT found at $BOOT_ACTIVITY_PATH"
        fi

        if [ -x "$SHUTDOWN_SCRIPT" ]; then
            echo "shutdown.sh exists and is executable"
        elif [ -f "$SHUTDOWN_SCRIPT" ]; then
            echo "shutdown.sh exists but is NOT executable"
        else
            echo "shutdown.sh NOT found at $SHUTDOWN_SCRIPT"
        fi

        # Check if host has exceeded maximum age (hard timeout)
        # This takes precedence over idle timeout to ensure clean shutdown before
        # external timeout (e.g., Modal sandbox timeout) kills the host
        if check_max_host_age; then
            # Call shutdown script if it exists
            if [ -x "$SHUTDOWN_SCRIPT" ]; then
                echo "Calling shutdown script due to max host age: $SHUTDOWN_SCRIPT"
                "$SHUTDOWN_SCRIPT"
                # Exit after calling shutdown (the script should handle the actual shutdown)
                exit 0
            else
                echo "Shutdown script not found or not executable: $SHUTDOWN_SCRIPT"
                # Continue monitoring in case the script appears later
            fi
        fi

        # Check if data.json exists
        if [ ! -f "$DATA_JSON_PATH" ]; then
            sleep "$CHECK_INTERVAL"
            continue
        fi

        # Read idle timeout from data.json
        local idle_timeout_seconds
        idle_timeout_seconds=$(get_idle_timeout_seconds)
        if [ -z "$idle_timeout_seconds" ]; then
            sleep "$CHECK_INTERVAL"
            continue
        fi

        # Check if activity sources are configured (DISABLED mode has empty array)
        local activity_sources
        activity_sources=$(get_activity_sources)
        if [ -z "$activity_sources" ]; then
            sleep "$CHECK_INTERVAL"
            continue
        fi

        # Get the maximum activity time
        local max_mtime
        max_mtime=$(get_max_activity_mtime)

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
