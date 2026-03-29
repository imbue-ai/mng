#!/usr/bin/env bash
#
# wait_for_stop_hook.sh
#
# A Claude Code Stop hook that waits for all other stop hooks to finish
# before proceeding. Exits when:
#   1. All other stop hooks have exited.
#
# Identification strategy:
#   All stop hooks and bash tool tasks are direct children of the Claude
#   process. They are distinguished by environment variables:
#     - Stop hooks: have CLAUDE_PROJECT_DIR in their environment
#     - Bash tool tasks: have CLAUDECODE=1 in their environment
#   We also skip node/claude internal processes.

set -euo pipefail

# --- Configuration (override via environment) ---
GRACE_PERIOD="${HOOK_GRACE_PERIOD:-3}"      # seconds before first check
POLL_INTERVAL="${HOOK_POLL_INTERVAL:-1}"    # seconds between polls

# Session guard: exit early if not a managed session
[ -z "${MAIN_CLAUDE_SESSION_ID:-}" ] && exit 0

# Drain stdin so we don't block Claude
cat > /dev/null 2>&1 || true

# --- Find the Claude ancestor process ---
find_claude_pid() {
    local pid=$$
    while [ "$pid" -gt 1 ] 2>/dev/null; do
        local comm
        comm=$(cat "/proc/$pid/comm" 2>/dev/null || echo "")
        if [ "$comm" = "claude" ]; then
            echo "$pid"
            return 0
        fi
        local next
        next=$(awk '/^PPid:/{print $2}' "/proc/$pid/status" 2>/dev/null || echo "")
        if [ -z "$next" ] || [ "$next" = "$pid" ]; then
            break
        fi
        pid=$next
    done
    return 1
}

# --- Identify our own wrapper (the direct child of Claude in our ancestry) ---
find_our_wrapper_pid() {
    local pid=$$
    local claude_pid=$1
    while [ "$pid" -gt 1 ] 2>/dev/null; do
        local ppid
        ppid=$(awk '/^PPid:/{print $2}' "/proc/$pid/status" 2>/dev/null || echo "")
        if [ "$ppid" = "$claude_pid" ]; then
            echo "$pid"
            return 0
        fi
        if [ -z "$ppid" ] || [ "$ppid" = "$pid" ]; then
            break
        fi
        pid=$ppid
    done
    echo "$PPID"
}

# --- Check if a process is a stop hook (has CLAUDE_PROJECT_DIR, not CLAUDECODE) ---
is_stop_hook() {
    local pid=$1
    # Must have CLAUDE_PROJECT_DIR
    if ! tr '\0' '\n' < "/proc/$pid/environ" 2>/dev/null | grep -q '^CLAUDE_PROJECT_DIR=' 2>/dev/null; then
        return 1
    fi
    # Must NOT have CLAUDECODE=1 (bash tool tasks)
    if tr '\0' '\n' < "/proc/$pid/environ" 2>/dev/null | grep -qx 'CLAUDECODE=1' 2>/dev/null; then
        return 1
    fi
    return 0
}

# --- Get list of other stop hook PIDs ---
get_other_stop_hooks() {
    local claude_pid=$1
    local our_wrapper=$2
    local result=()

    local children
    children=$(grep -l "^PPid:[[:space:]]*${claude_pid}$" /proc/[0-9]*/status 2>/dev/null | \
               sed 's|/proc/\([0-9]*\)/status|\1|' | sort -n || true)

    for child in $children; do
        [ -d "/proc/$child" ] || continue
        [ "$child" = "$our_wrapper" ] && continue
        is_stop_hook "$child" || continue
        result+=("$child")
    done

    echo "${result[*]}"
}

# --- Mark agent as inactive and emit activity event ---
mark_inactive() {
    rm -f "$MNGR_AGENT_STATE_DIR/active" "$MNGR_AGENT_STATE_DIR/permissions_waiting"
    mkdir -p "$MNGR_HOST_DIR/events/mngr/activity"
    echo '{"source": "mngr/activity", "type": "activity", "event_id": "evt-'"$(head -c 16 /dev/urandom | xxd -p)"'", "timestamp": "'"$(date -u +"%Y-%m-%dT%H:%M:%S.000000000Z")"'"}' \
        >> "$MNGR_HOST_DIR/events/mngr/activity/events.jsonl"
}

# =====================================================================
# Main
# =====================================================================

CLAUDE_PID=$(find_claude_pid) || {
    echo "wait_for_stop_hook: could not find Claude ancestor process" >&2
    exit 1
}

OUR_WRAPPER=$(find_our_wrapper_pid "$CLAUDE_PID")

echo "wait_for_stop_hook: Claude PID=$CLAUDE_PID, our wrapper=$OUR_WRAPPER, grace=${GRACE_PERIOD}s"

# Grace period: give Claude time to spawn all stop hooks
sleep "$GRACE_PERIOD"

# Snapshot the other stop hooks we need to wait for
INITIAL_HOOKS=$(get_other_stop_hooks "$CLAUDE_PID" "$OUR_WRAPPER")

if [ -z "$INITIAL_HOOKS" ]; then
    echo "wait_for_stop_hook: no other stop hooks found after grace period"
    mark_inactive
    exit 0
fi

echo "wait_for_stop_hook: waiting for stop hooks: $INITIAL_HOOKS"

while true; do
    ALL_DONE=true
    for hook_pid in $INITIAL_HOOKS; do
        if [ -d "/proc/$hook_pid" ]; then
            ALL_DONE=false
            break
        fi
    done

    if [ "$ALL_DONE" = true ]; then
        echo "wait_for_stop_hook: all other stop hooks have finished"
        mark_inactive
        exit 0
    fi

    sleep "$POLL_INTERVAL"
done
