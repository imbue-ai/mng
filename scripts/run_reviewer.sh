#!/usr/bin/env bash
#
# run_reviewer.sh
#
# Triggers a code review in a tmux reviewer window, waits for completion,
# and sorts the results.
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

STOP_HOOK_SCRIPT_NAME="run_reviewer:$WINDOW"
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/stop_hook_common.sh"

_log_to_file "INFO" "run_reviewer started (pid=$$, ppid=$PPID, session=$SESSION, window=$WINDOW)"

# Configuration
REVIEW_TIMEOUT=600  # 10 minutes max wait for review
POLL_INTERVAL=5     # Check every 5 seconds
REVIEW_OUTPUT_DIR=".reviews/final_issue_json"
REVIEW_OUTPUT_FILE="$REVIEW_OUTPUT_DIR/$WINDOW.json"
REVIEW_DONE_MARKER="$REVIEW_OUTPUT_FILE.done"

# Cache directory for skipping redundant reviews of the same commit
CACHE_DIR=".reviews/cache"
CACHE_COMMIT_FILE="$CACHE_DIR/$WINDOW.commit"
CACHE_OUTPUT_FILE="$CACHE_DIR/$WINDOW.json"
CACHE_EXIT_CODE_FILE="$CACHE_DIR/$WINDOW.exit_code"

# Check if the current commit has already been reviewed successfully
CURRENT_COMMIT=$(git rev-parse HEAD)
if [[ -f "$CACHE_COMMIT_FILE" && -f "$CACHE_OUTPUT_FILE" && -f "$CACHE_EXIT_CODE_FILE" ]]; then
    CACHED_COMMIT=$(cat "$CACHE_COMMIT_FILE")
    if [[ "$CURRENT_COMMIT" == "$CACHED_COMMIT" ]]; then
        CACHED_EXIT_CODE=$(cat "$CACHE_EXIT_CODE_FILE")
        # Restore the cached output file so callers can read it
        mkdir -p "$REVIEW_OUTPUT_DIR"
        cp "$CACHE_OUTPUT_FILE" "$REVIEW_OUTPUT_FILE"
        echo -e "[$WINDOW] Commit $CURRENT_COMMIT already reviewed -- using cached results (exit code $CACHED_EXIT_CODE)"
        _log_to_file "INFO" "Cache hit for commit $CURRENT_COMMIT, exiting with cached code $CACHED_EXIT_CODE"
        exit "$CACHED_EXIT_CODE"
    fi
fi

# remove old files and ensure directories exist
rm -rf "$REVIEW_DONE_MARKER"
rm -rf "$REVIEW_OUTPUT_FILE"
rm -rf ".reviews/initial_issue_list/$WINDOW.md"
mkdir -p .reviews/initial_issue_list .reviews/final_issue_json

# Override console log functions to include window name prefix
log_error() {
    echo -e "${RED}[$WINDOW] ERROR: $1${NC}" >&2
    _log_to_file "ERROR" "$1"
}

log_warn() {
    echo -e "${YELLOW}[$WINDOW] WARN: $1${NC}" >&2
    _log_to_file "WARN" "$1"
}

log_info() {
    echo -e "${GREEN}[$WINDOW] $1${NC}"
    _log_to_file "INFO" "$1"
}

# Send the review command to the tmux window
_log_to_file "INFO" "Sending review commands to tmux $SESSION:$WINDOW"
log_info "Triggering review in $SESSION:$WINDOW..."
tmux send-keys -t "$SESSION:$WINDOW" "/clear"
# see below note
sleep 1.0
tmux send-keys -t "$SESSION:$WINDOW" Enter
sleep 2.0
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
        _log_to_file "ERROR" "Timeout waiting for review after ${REVIEW_TIMEOUT}s, exiting with 3"
        exit 3
    fi

    if [[ -f "$REVIEW_DONE_MARKER" ]]; then
        ELAPSED=$((CURRENT_TIME - START_TIME))
        log_info "Review completed in ${ELAPSED}s"
        _log_to_file "INFO" "Review done marker found after ${ELAPSED}s"
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
    # Confidence may be numeric (0.0-1.0) or a string ("HIGH", "MEDIUM", "LOW")
    log_info "Sorting review results..."

    # Use flatten to normalize: if the reviewer outputs a JSON array instead of
    # JSONL, jq -s wraps it into [[...]], and sort_by(.severity) would fail with
    # "Cannot index array with string". flatten unwraps the nested array.
    jq -s 'flatten | sort_by(
      (if .severity == "CRITICAL" then 0
       elif .severity == "MAJOR" then 1
       elif .severity == "MINOR" then 2
       elif .severity == "NITPICK" then 3
       else 4 end),
      (if (.confidence | type) == "number" then -.confidence
       elif .confidence == "HIGH" then 0
       elif .confidence == "MEDIUM" then 1
       elif .confidence == "LOW" then 2
       else 3 end)
    )' "$REVIEW_OUTPUT_FILE" > "$SORTED_OUTPUT"
fi

# Copy sorted output back to the review output file for callers to read
cp "$SORTED_OUTPUT" "$REVIEW_OUTPUT_FILE"

# Check for blocking issues (CRITICAL or MAJOR severity with high confidence)
# Confidence may be numeric (>= 0.7) or a string ("HIGH")
BLOCKING_ISSUES=$(jq '[.[] | select(
    (.severity == "CRITICAL" or .severity == "MAJOR") and
    (((.confidence | type) == "number" and .confidence >= 0.7) or
     ((.confidence | type) == "string" and .confidence == "HIGH"))
)] | length' "$SORTED_OUTPUT")

# Cache the results so we can skip re-reviewing the same commit
cache_results() {
    local exit_code="$1"
    mkdir -p "$CACHE_DIR"
    echo "$CURRENT_COMMIT" > "$CACHE_COMMIT_FILE"
    cp "$SORTED_OUTPUT" "$CACHE_OUTPUT_FILE"
    echo "$exit_code" > "$CACHE_EXIT_CODE_FILE"
}

# Upload reviewer output to a Modal volume for data collection (best-effort).
# Tries two methods (both allowed to fail):
#   1. Direct copy to a mounted volume path + sync (works inside Modal sandbox)
#   2. Upload via `modal volume put` CLI (works when running locally)
UPLOAD_VOLUME_NAME="code-review-json"
UPLOAD_VOLUME_MOUNT="/code_reviews"

upload_reviewer_output() {
    local output_file="$1"
    local commit="$2"

    # Extract reviewer number from window name (e.g., "reviewer_0" -> "0")
    local reviewer_num="${WINDOW#reviewer_}"

    # Build nested directory path from commit hash to work around per-directory
    # file limits on Modal volumes.  First 4 chunks of 4 hex chars become
    # directory levels; the remaining 24 chars become the final directory.
    # e.g. 63dced2455b3a9a54942169b02273ac568757f8e
    #   -> 63dc/ed24/55b3/a9a5/4942169b02273ac568757f8e/
    local nested_path="${commit:0:4}/${commit:4:4}/${commit:8:4}/${commit:12:4}/${commit:16}"
    local filename="${reviewer_num}.json"

    # Method 1: Copy to mounted volume + sync (Modal sandbox)
    local mount_dir="${UPLOAD_VOLUME_MOUNT}/${nested_path}"
    if mkdir -p "${mount_dir}" 2>/dev/null && cp "$output_file" "${mount_dir}/${filename}" 2>/dev/null; then
        if sync "${UPLOAD_VOLUME_MOUNT}" 2>/dev/null; then
            log_info "Uploaded reviewer output to mounted volume at ${mount_dir}/${filename}"
        else
            log_warn "Copied to mounted volume but sync failed"
        fi
    else
        log_warn "Direct volume copy failed (expected if not running in Modal)"
    fi

    # Method 2: Upload via modal CLI (local machine with Modal credentials)
    if uv run modal volume put "${UPLOAD_VOLUME_NAME}" "$output_file" "/${nested_path}/${filename}" --force 2>/dev/null; then
        log_info "Uploaded reviewer output via modal volume put"
    else
        log_warn "modal volume put failed (expected if not running locally with Modal credentials)"
    fi
}

if [[ "$BLOCKING_ISSUES" -gt 0 ]]; then
    log_error "Found $BLOCKING_ISSUES blocking issues (CRITICAL/MAJOR with confidence >= 0.7)"
    cache_results 2
    _log_to_file "INFO" "Found $BLOCKING_ISSUES blocking issues, exiting with 2"
    exit 2
fi

log_info "Reviewer $WINDOW completed successfully (no blocking issues)"
upload_reviewer_output "$REVIEW_OUTPUT_FILE" "$CURRENT_COMMIT"
cache_results 0
_log_to_file "INFO" "run_reviewer completed successfully, exiting with 0"
exit 0
