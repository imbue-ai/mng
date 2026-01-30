#!/bin/bash
# Activity watcher script for mngr hosts.
# This script monitors activity files and calls shutdown.sh when the host becomes idle.
#
# Usage: activity_watcher.sh <host_data_dir>
#
# The script reads:
#   - <host_data_dir>/activity_files: newline-delimited list of file patterns to monitor
#   - <host_data_dir>/idle_timeout: the idle timeout in seconds
#   - <host_data_dir>/max_host_age: (optional) maximum host age in seconds from boot
#
# When the maximum mtime of all matched files + idle_timeout < current_time,
# the script calls <host_data_dir>/commands/shutdown.sh.
#
# Additionally, if max_host_age exists, the script will trigger shutdown when:
#   current_time > boot_activity_file_mtime + max_host_age_seconds
# This ensures the host shuts down cleanly before external timeouts (e.g., Modal sandbox timeout).

set -e

HOST_DATA_DIR="$1"

if [ -z "$HOST_DATA_DIR" ]; then
    echo "Usage: activity_watcher.sh <host_data_dir>" >&2
    exit 1
fi

ACTIVITY_FILES_PATH="$HOST_DATA_DIR/activity_files"
IDLE_TIMEOUT_PATH="$HOST_DATA_DIR/idle_timeout"
MAX_HOST_AGE_PATH="$HOST_DATA_DIR/max_host_age"
BOOT_ACTIVITY_PATH="$HOST_DATA_DIR/activity/boot"
SHUTDOWN_SCRIPT="$HOST_DATA_DIR/commands/shutdown.sh"
CHECK_INTERVAL=60

# Get the mtime of a file as Unix timestamp, or empty string if file doesn't exist
get_mtime() {
    local file="$1"
    if [ -f "$file" ]; then
        # Try Linux stat first, then macOS stat
        stat -c %Y "$file" 2>/dev/null || stat -f %m "$file" 2>/dev/null || echo ""
    fi
}

# Check if the host has exceeded its maximum age (hard timeout)
# Returns 0 (true) if the host should be shut down due to age, 1 (false) otherwise
check_max_host_age() {
    # If no max_host_age file exists, no hard timeout applies
    if [ ! -f "$MAX_HOST_AGE_PATH" ]; then
        return 1
    fi

    # Read max host age
    local max_host_age_seconds
    max_host_age_seconds=$(cat "$MAX_HOST_AGE_PATH")
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

# Get the maximum mtime across all activity files matching the patterns
get_max_activity_mtime() {
    local max_mtime=0

    # Read patterns from activity_files, expand globs, and check mtimes
    while IFS= read -r pattern || [ -n "$pattern" ]; do
        # Skip empty lines
        [ -z "$pattern" ] && continue

        # Expand the glob pattern (handles both explicit paths and wildcards)
        # shellcheck disable=SC2086
        for file in $pattern; do
            if [ -f "$file" ]; then
                local mtime
                mtime=$(get_mtime "$file")
                if [ -n "$mtime" ] && [ "$mtime" -gt "$max_mtime" ]; then
                    max_mtime=$mtime
                fi
            fi
        done
    done < "$ACTIVITY_FILES_PATH"

    echo "$max_mtime"
}

main() {
    echo "Activity watcher starting for $HOST_DATA_DIR"

    while true; do
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

        # Check if activity_files exists (DISABLED mode has empty file)
        if [ ! -f "$ACTIVITY_FILES_PATH" ]; then
            sleep "$CHECK_INTERVAL"
            continue
        fi

        # Read idle timeout
        if [ ! -f "$IDLE_TIMEOUT_PATH" ]; then
            sleep "$CHECK_INTERVAL"
            continue
        fi
        local idle_timeout_seconds
        idle_timeout_seconds=$(cat "$IDLE_TIMEOUT_PATH")

        # Check if activity_files is empty (DISABLED mode)
        if [ ! -s "$ACTIVITY_FILES_PATH" ]; then
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
