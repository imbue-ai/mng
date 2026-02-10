#!/bin/bash
#
# stop_hook_common.sh
#
# Shared function definitions for stop hook scripts. Source this file to get
# logging helpers and retry_command. No side effects -- just definitions.

# Colors for output (disabled if not a terminal)
if [[ -t 2 ]]; then
    RED='\033[0;31m'
    GREEN='\033[0;32m'
    YELLOW='\033[0;33m'
    NC='\033[0m'
else
    RED=''
    GREEN=''
    YELLOW=''
    NC=''
fi

log_error() {
    echo -e "${RED}ERROR: $1${NC}" >&2
}

log_warn() {
    echo -e "${YELLOW}WARN: $1${NC}" >&2
}

log_info() {
    echo -e "${GREEN}$1${NC}"
}

# Retry a command with exponential backoff
# Usage: retry_command <max_retries> <command...>
retry_command() {
    local max_retries=$1
    shift
    local attempt=1
    local wait_time=1

    while [[ $attempt -le $max_retries ]]; do
        if "$@"; then
            return 0
        fi

        if [[ $attempt -lt $max_retries ]]; then
            log_warn "Command failed (attempt $attempt/$max_retries), retrying in ${wait_time}s..."
            sleep "$wait_time"
            wait_time=$((wait_time * 2))
        fi
        attempt=$((attempt + 1))
    done

    log_error "Command failed after $max_retries attempts: $*"
    return 1
}
