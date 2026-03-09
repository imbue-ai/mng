#!/bin/bash
# Stop hook that requires /autofix to be run before the agent can stop.
# Reads configuration from .autofix/config/stop-hook.toml.
set -euo pipefail

CONFIG_FILE=".autofix/config/stop-hook.toml"

# Read config values (simple key = value parsing, no TOML library needed)
_read_config() {
    local key="$1"
    local default="$2"
    if [ -f "$CONFIG_FILE" ]; then
        local val
        val=$(grep "^${key} " "$CONFIG_FILE" 2>/dev/null | head -1 | sed 's/^[^=]*= *//' | sed 's/^"//;s/"$//')
        if [ -n "$val" ]; then
            echo "$val"
            return
        fi
    fi
    echo "$default"
}

ENABLED=$(_read_config "enabled" "true")
if [ "$ENABLED" != "true" ]; then
    exit 0
fi

HASH=$(git rev-parse HEAD 2>/dev/null) || exit 0

if [ -f ".autofix/plans/${HASH}_verified.md" ]; then
    exit 0
fi

EXTRA_ARGS=$(_read_config "extra_args" "")

if [ -n "$EXTRA_ARGS" ]; then
    echo "To verify your changes, run: \"/autofix ${EXTRA_ARGS}\"" >&2
else
    echo "To verify your changes, run: \"/autofix\"" >&2
fi
exit 2
