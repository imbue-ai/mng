#!/usr/bin/env bash
# Gate check: requires /autofix to be run before the agent can stop.
# Reads configuration from .autofix/config/stop-hook.json,
# with optional local overrides from stop-hook.local.json.
# Called by main_claude_stop_hook.sh before PR creation.
# Stuck agent tracking is handled by the caller.
set -euo pipefail

# shellcheck source=config_utils.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/config_utils.sh"

CONFIG_FILE=".autofix/config/stop-hook.json"

ENABLED=$(read_json_config "$CONFIG_FILE" "enabled" "true")
if [ "$ENABLED" != "true" ]; then
    exit 0
fi

HASH=$(git rev-parse HEAD 2>/dev/null) || exit 0

if [ -f ".autofix/plans/${HASH}_verified.md" ]; then
    exit 0
fi

EXTRA_ARGS=$(read_json_config "$CONFIG_FILE" "extra_args" "")

if [ -n "$EXTRA_ARGS" ]; then
    echo "To verify your changes, run: \"/autofix ${EXTRA_ARGS}\"" >&2
else
    echo "To verify your changes, run: \"/autofix\"" >&2
fi
exit 2
