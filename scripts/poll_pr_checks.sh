#!/usr/bin/env bash
#
# poll_pr_checks.sh
#
# Polls GitHub waiting for PR checks to complete, then reports the result.
#
# Usage: ./poll_pr_checks.sh <branch_name_or_pr_number>
#
# Options:
#   --timeout <seconds>   Maximum time to wait (default: 600 = 10 minutes)
#   --interval <seconds>  Polling interval (default: 15)
#
# Output:
#   Prints "success" if all checks passed
#   Prints "failure" if any check failed
#   Exits with code 1 on timeout or error

set -euo pipefail

# Defaults
TIMEOUT=600
INTERVAL=15

# Parse arguments
POSITIONAL_ARGS=()
while [[ $# -gt 0 ]]; do
    case $1 in
        --timeout)
            TIMEOUT="$2"
            shift 2
            ;;
        --interval)
            INTERVAL="$2"
            shift 2
            ;;
        -*)
            echo "Unknown option: $1" >&2
            exit 1
            ;;
        *)
            POSITIONAL_ARGS+=("$1")
            shift
            ;;
    esac
done

set -- "${POSITIONAL_ARGS[@]}"

if [[ $# -lt 1 ]]; then
    echo "Usage: $0 [--timeout <seconds>] [--interval <seconds>] <branch_name_or_pr_number>" >&2
    exit 1
fi

BRANCH_OR_PR="$1"

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

# File logging (uses STOP_HOOK_LOG exported by main_stop_hook)
_log_to_file() {
    local level="$1"
    local msg="$2"
    if [[ -n "${STOP_HOOK_LOG:-}" ]]; then
        local ts
        ts=$(date '+%Y-%m-%d %H:%M:%S')
        echo "[$ts] [$$] [poll_pr_checks] [$level] $msg" >> "$STOP_HOOK_LOG"
    fi
}

log_info() {
    echo -e "${GREEN}$1${NC}"
    _log_to_file "INFO" "$1"
}

log_warn() {
    echo -e "${YELLOW}$1${NC}" >&2
    _log_to_file "WARN" "$1"
}

log_error() {
    echo -e "${RED}ERROR: $1${NC}" >&2
    _log_to_file "ERROR" "$1"
}

_log_to_file "INFO" "poll_pr_checks started (pid=$$, ppid=$PPID, arg=$BRANCH_OR_PR, timeout=$TIMEOUT, interval=$INTERVAL)"

# Resolve PR number from branch name if needed
PR_NUMBER=""
if [[ "$BRANCH_OR_PR" =~ ^[0-9]+$ ]]; then
    PR_NUMBER="$BRANCH_OR_PR"
else
    log_info "Looking up PR for branch: $BRANCH_OR_PR"
    if ! PR_NUMBER=$(gh pr view "$BRANCH_OR_PR" --json number --jq '.number' 2>&1); then
        log_error "No PR found for branch: $BRANCH_OR_PR"
        exit 1
    fi
fi

log_info "Monitoring PR #$PR_NUMBER"

# Get the head SHA of the PR to check
HEAD_SHA=$(gh pr view "$PR_NUMBER" --json headRefOid --jq '.headRefOid')
log_info "Head SHA: $HEAD_SHA"

START_TIME=$(date +%s)
END_TIME=$((START_TIME + TIMEOUT))

while true; do
    CURRENT_TIME=$(date +%s)

    if [[ $CURRENT_TIME -ge $END_TIME ]]; then
        log_error "Timeout waiting for checks to complete after ${TIMEOUT}s"
        _log_to_file "ERROR" "Timeout after ${TIMEOUT}s, exiting with 1"
        exit 1
    fi

    ELAPSED=$((CURRENT_TIME - START_TIME))

    # Get check status using gh pr checks
    # This returns the combined status of all checks
    # gh pr checks exits with 1 if any checks failed, so we capture output regardless
    CHECK_OUTPUT=""
    if ! CHECK_OUTPUT=$(gh pr checks "$PR_NUMBER" 2>&1); then
        # gh pr checks returns non-zero if checks failed or no checks exist
        # We need to distinguish between these cases
        if [[ -z "$CHECK_OUTPUT" ]] || echo "$CHECK_OUTPUT" | grep -qE "no checks reported|no checks"; then
            log_warn "No checks found yet (${ELAPSED}s elapsed), waiting..."
            sleep "$INTERVAL"
            continue
        fi
        # Otherwise, we have check output but some checks failed - continue to process it
    fi

    # Check if there are any checks at all
    if [[ -z "$CHECK_OUTPUT" ]] || echo "$CHECK_OUTPUT" | grep -qE "no checks reported|no checks"; then
        log_warn "No checks found yet (${ELAPSED}s elapsed), waiting..."
        sleep "$INTERVAL"
        continue
    fi

    # Count the status of checks
    # gh pr checks output format: "check_name<tab>status<tab>duration<tab>url"
    # grep -c outputs "0" and exits 1 when no matches; || true suppresses the
    # exit code while keeping the "0" output (using || echo 0 would double it).
    PENDING_COUNT=$(echo "$CHECK_OUTPUT" | grep -cE "pending|queued|in_progress|waiting" || true)
    FAILED_COUNT=$(echo "$CHECK_OUTPUT" | grep -cE "fail|error|cancelled|timed_out|action_required|stale" || true)
    PASSED_COUNT=$(echo "$CHECK_OUTPUT" | grep -cE "pass|success|neutral|skipped" || true)

    log_info "Check status (${ELAPSED}s elapsed): $PASSED_COUNT passed, $FAILED_COUNT failed, $PENDING_COUNT pending"

    # If there are still pending checks, wait
    if [[ $PENDING_COUNT -gt 0 ]]; then
        sleep "$INTERVAL"
        continue
    fi

    _log_to_file "INFO" "Check status (${ELAPSED}s): passed=$PASSED_COUNT, failed=$FAILED_COUNT, pending=$PENDING_COUNT"

    # All checks have completed
    if [[ $FAILED_COUNT -gt 0 ]]; then
        log_error "Some checks failed"
        _log_to_file "ERROR" "Some checks failed, exiting with 1"
        echo "failure"
        exit 1
    fi

    log_info "All checks passed"
    _log_to_file "INFO" "All checks passed, exiting with 0"
    echo "success"
    exit 0
done
