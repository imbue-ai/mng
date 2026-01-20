#!/usr/bin/env bash
#
# run_reviewer.sh
#
# Triggers a code review in a tmux reviewer window, waits for completion,
# sorts the results, and stores them in git LFS with a git note.
#
# Usage: ./run_reviewer.sh <session> <window>
#
# Arguments:
#   session  - tmux session name
#   window   - tmux window name (e.g., reviewer_0)

set -euo pipefail

if [[ $# -lt 2 ]]; then
    echo "Usage: $0 <session> <window>" >&2
    exit 1
fi

SESSION="$1"
WINDOW="$2"

# Get the directory of this script
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Configuration
REVIEW_TIMEOUT=600  # 10 minutes max wait for review
POLL_INTERVAL=5     # Check every 5 seconds
REVIEW_OUTPUT_DIR=".reviews/final_issue_json"
REVIEW_OUTPUT_FILE="$REVIEW_OUTPUT_DIR/$WINDOW.json"
REVIEW_DONE_MARKER="$REVIEW_OUTPUT_FILE.done"

# remove the old files
rm -rf $REVIEW_DONE_MARKER
rm -rf $REVIEW_OUTPUT_FILE

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
    echo -e "${RED}[$WINDOW] ERROR: $1${NC}" >&2
}

log_warn() {
    echo -e "${YELLOW}[$WINDOW] WARN: $1${NC}" >&2
}

log_info() {
    echo -e "${GREEN}[$WINDOW] $1${NC}"
}

# Send the review command to the tmux window
log_info "Triggering review in $SESSION:$WINDOW..."
tmux send-keys -t "$SESSION:$WINDOW" "/verify-branch"
# These have to be separate - otherwise it's treated as a bracketed paste
# and irritatingly, we *do* require the sleep :(  I've seen claude fail without this (though even with zero sleep it only fails about 1 in 10 times for me)
# it would clearly be better to have a more robust method for sending messages, but we don't quite have that yet
sleep 1.0
tmux send-keys -t "$SESSION:$WINDOW" Enter

# Wait for the review done marker file to be created
log_info "Waiting for review to complete..."
START_TIME=$(date +%s)
END_TIME=$((START_TIME + REVIEW_TIMEOUT))

while true; do
    CURRENT_TIME=$(date +%s)

    if [[ $CURRENT_TIME -ge $END_TIME ]]; then
        log_error "Timeout waiting for review after ${REVIEW_TIMEOUT}s"
        exit 3
    fi

    if [[ -f "$REVIEW_DONE_MARKER" ]]; then
        ELAPSED=$((CURRENT_TIME - START_TIME))
        log_info "Review completed in ${ELAPSED}s"
        break
    fi

    sleep "$POLL_INTERVAL"
done

SORTED_OUTPUT=$(mktemp).json
trap "rm -f '$SORTED_OUTPUT'" EXIT

# if the output file doesn't exist or is empty:
if [[ ! -s "$REVIEW_OUTPUT_FILE" ]]; then
    log_info "Done marker exists but output file not found, creating empty file (no issues found)"
    mkdir -p "$REVIEW_OUTPUT_DIR"
    echo '[]' > "$SORTED_OUTPUT"
else
    # Sort the JSON by severity (most severe first), then by confidence (high to low)
    # Severity order: CRITICAL > MAJOR > MINOR > NITPICK > unknown
    # Confidence is a numeric value from 0.0 to 1.0 (higher = more confident)
    log_info "Sorting review results..."

    jq -s 'sort_by(
      (if .severity == "CRITICAL" then 0
       elif .severity == "MAJOR" then 1
       elif .severity == "MINOR" then 2
       elif .severity == "NITPICK" then 3
       else 4 end),
      (-.confidence)
    )' "$REVIEW_OUTPUT_FILE" > "$SORTED_OUTPUT"
fi

# Store the sorted JSON in git LFS
FILE_TYPE="issues/verify_branch/$WINDOW"
log_info "Storing review results with FILE_TYPE: $FILE_TYPE"

if OUTPUT=$("$SCRIPT_DIR/add_commit_metadata_file.sh" "$SORTED_OUTPUT" "$FILE_TYPE" 2>&1); then
    RAW_URL=$(echo "$OUTPUT" | grep "raw.githubusercontent.com" | sed 's/^[[:space:]]*//')
    log_info "Review results stored successfully"

    if [[ -n "$RAW_URL" ]]; then
        # Create git note for the review results
        COMMIT_SHA=$(git rev-parse HEAD)
        log_info "Creating git note for review results..."
        git notes --ref="$FILE_TYPE" add -f -m "$RAW_URL" "$COMMIT_SHA"

        # Push the note
        log_info "Pushing git note..."
        if ! git push --force origin "refs/notes/$FILE_TYPE"; then
            log_warn "Failed to push git note"
        fi
    else
        log_warn "Could not extract URL from output"
    fi
else
    log_error "Failed to store review results: $OUTPUT"
    exit 1
fi

# Check for blocking issues (CRITICAL or MAJOR severity with confidence >= 0.7)
BLOCKING_ISSUES=$(jq '[.[] | select(
    (.severity == "CRITICAL" or .severity == "MAJOR") and
    (.confidence >= 0.7)
)] | length' "$SORTED_OUTPUT")

if [[ "$BLOCKING_ISSUES" -gt 0 ]]; then
    log_error "Found $BLOCKING_ISSUES blocking issues (CRITICAL/MAJOR with confidence >= 0.7)"
    exit 2
fi

log_info "Reviewer $WINDOW completed successfully (no blocking issues)"
exit 0
