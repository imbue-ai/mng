#!/bin/bash
# Stop hook script that messages reviewer tmux windows
# Only runs if the git repo is clean (all changes committed)

set -euo pipefail

# Remove the active session marker file on exit (regardless of success/failure)
cleanup_active_file() {
    rm -f .claude/active
}
trap cleanup_active_file EXIT

# Check if git repo is clean
untracked=$(git ls-files --others --exclude-standard)
staged=$(git diff --cached --name-only)
unstaged=$(git diff --name-only)

# If repo is not clean, exit silently (the check_commit_status.sh hook will handle the error)
if [ -n "$untracked" ] || [ -n "$staged" ] || [ -n "$unstaged" ]; then
    exit 0
fi

# Check if we're in a tmux session
if [ -z "${TMUX:-}" ]; then
    exit 0
fi

# Make sure we're the main claude session
if [ -z "${MAIN_CLAUDE_SESSION_ID:-}" ]; then
    # if not, this is a reviewer or some other random claude
    exit 0
fi

# make the session id accessible to the reviewers
echo $MAIN_CLAUDE_SESSION_ID > .claude/sessionid

# Track the commit hash we're reviewing (to detect stuck agents)
mkdir -p .claude
( git rev-parse HEAD || echo "conflict" ) >> .claude/reviewed_commits

# Check if we've reviewed the same commit 3 times in a row (agent is stuck)
if [[ -f .claude/reviewed_commits ]]; then
    # Get the last 3 entries
    LAST_THREE=$(tail -n 3 .claude/reviewed_commits)
    ENTRY_COUNT=$(echo "$LAST_THREE" | wc -l)

    if [[ $ENTRY_COUNT -ge 3 ]]; then
        # Check if all 3 entries are identical
        UNIQUE_COUNT=$(echo "$LAST_THREE" | sort -u | wc -l)
        if [[ $UNIQUE_COUNT -eq 1 ]]; then
            echo "ERROR: This hook has been run 3 times at the same commit." >&2
            echo "ERROR: The agent appears to be stuck and unable to make progress." >&2
            echo "ERROR: Please investigate and resolve the issue manually." >&2
            exit 1
        fi
    fi
fi

# Get the current tmux session name
session=$(tmux display-message -p '#S' 2>/dev/null)
if [ -z "$session" ]; then
    exit 0
fi

# Get the directory of this script (needed for launching reviewer scripts)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# convert jsonl conversation transcript to html
uv run --project contrib/claude-code-transcripts/ claude-code-transcripts json -o /tmp/transcript/$MAIN_CLAUDE_SESSION_ID `find ~/.claude/projects/ -name "$MAIN_CLAUDE_SESSION_ID.jsonl"`

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

# Store HTML transcript in git LFS
HTML_TRANSCRIPT="/tmp/transcript/$MAIN_CLAUDE_SESSION_ID/page-001.html"
HTML_RAW_URL=""
HTML_WEB_URL=""
if [[ -f "$HTML_TRANSCRIPT" ]]; then
    log_info "Storing HTML transcript in git LFS..."
    if HTML_OUTPUT=$("$SCRIPT_DIR/add_commit_metadata_file.sh" "$HTML_TRANSCRIPT" "transcripts/html" 2>&1); then
        HTML_RAW_URL=$(echo "$HTML_OUTPUT" | grep "raw.githubusercontent.com" | sed 's/^[[:space:]]*//')
        HTML_WEB_URL=$(echo "$HTML_OUTPUT" | grep "github.com/.*blob" | sed 's/^[[:space:]]*//')
        log_info "HTML transcript stored successfully"
        if [[ -z "$HTML_WEB_URL" ]]; then
            log_warn "Could not extract HTML web URL from output"
            log_warn "Output was: $HTML_OUTPUT"
        else
            log_info "HTML web URL: $HTML_WEB_URL"
        fi
    else
        log_error "Failed to store HTML transcript: $HTML_OUTPUT"
        exit 1
    fi
else
    log_warn "HTML transcript not found at $HTML_TRANSCRIPT"
fi

# Store JSON transcript in git LFS
JSON_TRANSCRIPT=$(find ~/.claude/projects/ -name "$MAIN_CLAUDE_SESSION_ID.jsonl" 2>/dev/null | head -1)
JSON_RAW_URL=""
if [[ -n "$JSON_TRANSCRIPT" && -f "$JSON_TRANSCRIPT" ]]; then
    log_info "Storing JSON transcript in git LFS..."
    if JSON_OUTPUT=$("$SCRIPT_DIR/add_commit_metadata_file.sh" "$JSON_TRANSCRIPT" "transcripts/json" 2>&1); then
        JSON_RAW_URL=$(echo "$JSON_OUTPUT" | grep "raw.githubusercontent.com" | sed 's/^[[:space:]]*//')
        log_info "JSON transcript stored successfully"
    else
        log_error "Failed to store JSON transcript: $JSON_OUTPUT"
        exit 1
    fi
fi

# Create git notes for the transcript URLs
COMMIT_SHA=$(git rev-parse HEAD)

if [[ -n "$HTML_RAW_URL" ]]; then
    log_info "Creating git note for HTML transcript..."
    git notes --ref=transcripts/html add -f -m "$HTML_RAW_URL" "$COMMIT_SHA"
fi

if [[ -n "$JSON_RAW_URL" ]]; then
    log_info "Creating git note for JSON transcript..."
    git notes --ref=transcripts/json add -f -m "$JSON_RAW_URL" "$COMMIT_SHA"
fi

# Push commits with retry logic
log_info "Pushing commits to origin..."
if ! retry_command 3 git push origin HEAD; then
    log_error "Failed to push commits after retries"
    exit 1
fi

# Push notes with force (notes can be force-pushed safely)
log_info "Pushing git notes to origin..."
if ! git push --force origin "refs/notes/*"; then
    log_warn "Failed to push git notes"
fi

# Ensure a PR exists for this branch
CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD)
BASE_BRANCH="${GIT_BASE_BRANCH:-main}"

# Ensure the base branch is pushed as well (otherwise cannot make the PR)
log_info "Ensuring base branch is on origin..."
if ! retry_command 3 git push origin $BASE_BRANCH; then
    log_error "Failed to push base branch after retries"
    exit 1
fi

# Check if there are any commits ahead of base branch (skip PR if purely informational)
IS_INFORMATIONAL_ONLY=false
if [[ "$CURRENT_BRANCH" == "$BASE_BRANCH" ]]; then
    log_info "Currently on base branch ($BASE_BRANCH) - no PR needed"
    IS_INFORMATIONAL_ONLY=true
elif COMMITS_AHEAD=$(git rev-list --count "origin/$BASE_BRANCH..HEAD" 2>/dev/null); then
    if [[ "$COMMITS_AHEAD" == "0" ]]; then
        log_info "No commits ahead of $BASE_BRANCH - this was an informational session, skipping PR creation"
        IS_INFORMATIONAL_ONLY=true
    fi
fi

# Find all windows named reviewer_* and start review processes as background jobs
REVIEWER_PIDS=()
for window in $(tmux list-windows -t "$session" -F '#W' 2>/dev/null | grep '^reviewer_' || true); do
    "$SCRIPT_DIR/run_reviewer.sh" "$session" "$window" &
    REVIEWER_PIDS+=($!)
done

# Helper function to create a new PR
# Returns the PR number on success, exits with error on failure
create_new_pr() {
    local pr_title="$1"
    local html_url="${2:-}"

    local pr_body="Automated PR created by Claude Code session.

## Transcript"
    if [[ -n "$html_url" ]]; then
        pr_body+="
- [View HTML Transcript]($html_url)"
    fi

    if gh pr create --base "$BASE_BRANCH" --head "$CURRENT_BRANCH" --title "$pr_title" --body "$pr_body" > /dev/null; then
        # Get the PR number after creation
        if PR_OUTPUT=$(gh pr view "$CURRENT_BRANCH" --json number --jq '.number' 2>/dev/null); then
            echo "$PR_OUTPUT"
            return 0
        fi
    fi
    return 1
}

# Skip PR creation and polling if this was an informational-only session
EXISTING_PR=""
PR_WAS_CREATED=false
if [[ "$IS_INFORMATIONAL_ONLY" == "false" ]]; then
    # Check if PR already exists
    log_info "Checking for existing PR..."
    PR_STATE=""
    if PR_INFO=$(gh pr view "$CURRENT_BRANCH" --json number,state 2>/dev/null); then
        EXISTING_PR=$(echo "$PR_INFO" | jq -r '.number')
        PR_STATE=$(echo "$PR_INFO" | jq -r '.state')
        log_info "Found existing PR #$EXISTING_PR (state: $PR_STATE)"
    fi

    if [[ -z "$EXISTING_PR" ]]; then
        # No PR exists - create a new one
        log_info "Creating new PR..."
        if NEW_PR=$(create_new_pr "$CURRENT_BRANCH" "$HTML_WEB_URL"); then
            EXISTING_PR="$NEW_PR"
            PR_WAS_CREATED=true
            log_info "Created PR #$EXISTING_PR"
        else
            log_error "Failed to create PR"
            exit 1
        fi
    elif [[ "$PR_STATE" == "MERGED" ]]; then
        # PR was merged - need to create a new one (can't reopen merged PRs on GitHub)
        log_info "PR #$EXISTING_PR is merged. Creating a new PR..."
        # Use a different title to distinguish from the merged PR
        NEW_TITLE="${CURRENT_BRANCH} (subsequent)"
        if NEW_PR=$(create_new_pr "$NEW_TITLE" "$HTML_WEB_URL"); then
            EXISTING_PR="$NEW_PR"
            PR_WAS_CREATED=true
            log_info "Created new PR #$EXISTING_PR (previous PR was merged)"
        else
            log_error "Failed to create new PR after merge"
            exit 1
        fi
    elif [[ "$PR_STATE" == "CLOSED" ]]; then
        # PR was closed but not merged - reopen it
        log_info "PR #$EXISTING_PR is closed. Reopening..."
        if gh pr reopen "$EXISTING_PR" --comment "Reopening PR for continued work."; then
            log_info "Reopened PR #$EXISTING_PR"
        else
            log_error "Failed to reopen PR #$EXISTING_PR"
            exit 1
        fi
    fi

    # Write PR URL to .claude/pr_url for status line display
    if [[ -n "$EXISTING_PR" ]]; then
        PR_URL=$(gh pr view "$EXISTING_PR" --json url --jq '.url' 2>/dev/null || echo "")
        if [[ -n "$PR_URL" ]]; then
            echo "$PR_URL" > .claude/pr_url
            log_info "Wrote PR URL to .claude/pr_url: $PR_URL"
        fi
        # Initialize PR status as pending before polling
        echo "pending" > .claude/pr_status
    fi

    # Update existing PR description with transcript link (only for pre-existing PRs, not newly created ones)
    if [[ -n "$EXISTING_PR" && "$PR_WAS_CREATED" == "false" && -n "$HTML_WEB_URL" ]]; then
        log_info "Updating PR #$EXISTING_PR with transcript link..."

        # Get current PR body
        if ! CURRENT_BODY=$(gh pr view "$EXISTING_PR" --json body --jq '.body'); then
            log_error "Failed to get current PR body"
            exit 1
        else
            # Build new transcript section
            TRANSCRIPT_SECTION="## Transcript
- [View HTML Transcript]($HTML_WEB_URL)"

            # Remove existing transcript section if present (everything from "## Transcript" to next "##" or end)
            # and append new one
            if echo "$CURRENT_BODY" | grep -q "## Transcript"; then
                # Use awk to remove the old transcript section
                NEW_BODY=$(echo "$CURRENT_BODY" | awk '
                    /^## Transcript/ { in_transcript=1; next }
                    /^## / && in_transcript { in_transcript=0 }
                    !in_transcript { print }
                ')
                NEW_BODY="$NEW_BODY
$TRANSCRIPT_SECTION"
            else
                # Add transcript section at the end
                NEW_BODY="$CURRENT_BODY

$TRANSCRIPT_SECTION"
            fi

            if gh pr edit "$EXISTING_PR" --body "$NEW_BODY"; then
                log_info "PR description updated successfully"
            else
                log_error "Failed to update PR description"
                exit 1
            fi
        fi
    fi

    # Poll for PR checks to complete and report result
    if [[ -n "$EXISTING_PR" ]]; then
        log_info "Polling for PR check results..."
        if RESULT=$("$SCRIPT_DIR/poll_pr_checks.sh" "$EXISTING_PR"); then
            echo "$RESULT"
            # Write successful status to .claude/pr_status
            echo "success" > .claude/pr_status
            log_info "Wrote PR status to .claude/pr_status: success"
        else
            # Write failure status to .claude/pr_status
            echo "failure" > .claude/pr_status
            log_info "Wrote PR status to .claude/pr_status: failure"
            log_error "The tests have failed for the PR that was created by this script!"
            log_error "Use the gh tool to inspect the remote test results for this branch and see what failed."
            log_error "Note that you MUST identify the issue and fix it locally before trying again!"
            log_error "NEVER just re-trigger the pipeline!"
            log_error "NEVER fix timeouts by increasing them! Instead, make things faster or increase parallelism."
            log_error "If it is impossible to fix the test, tell the user and say that you failed."
            log_error "Otherwise, once you have understood and fixed the issue, you can simply commit to try again."
            exit 2
        fi
    fi
fi

# Wait for all reviewer background jobs to complete
REVIEWER_WINDOWS=()
if [[ ${#REVIEWER_PIDS[@]} -gt 0 ]]; then
    log_info "Waiting for ${#REVIEWER_PIDS[@]} reviewer(s) to complete..."
    REVIEWER_FAILED=false

    # Collect reviewer windows for later
    for window in $(tmux list-windows -t "$session" -F '#W' 2>/dev/null | grep '^reviewer_' || true); do
        REVIEWER_WINDOWS+=("$window")
    done

    for pid in "${REVIEWER_PIDS[@]}"; do
        wait "$pid" && EXIT_CODE=0 || EXIT_CODE=$?
        if [[ $EXIT_CODE -ne 0 ]]; then
            if [[ $EXIT_CODE -eq 2 ]]; then
                # Exit code 2 means the reviewer found blocking issues (CRITICAL/MAJOR with confidence >= 0.7)
                # This is expected behavior - we'll surface it to the user after all reviewers complete
                log_warn "Reviewer process $pid found blocking issues (exit code 2)"
                REVIEWER_FAILED=true
            else
                # Other exit codes indicate internal errors that should be surfaced immediately
                # Exit code 1 = failed to store review results
                # Exit code 3 = timeout waiting for review
                log_error "Reviewer process $pid failed with internal error (exit code $EXIT_CODE)"
                log_error "This indicates a problem with the review infrastructure, not code issues."
                log_error "Exit code 1 = failed to store review results"
                log_error "Exit code 3 = timeout waiting for review"
                exit $EXIT_CODE
            fi
        fi
    done
    if [[ "$REVIEWER_FAILED" == true ]]; then
        log_error "Some issue were identified by the review agent!"
        log_error "Run 'cat .reviews/final_issue_json/*.json' to see the issues."
        log_error "You MUST fix any CRITICAL or MAJOR issues (with confidence >= 0.7) before trying again."
        exit 2
    else
        log_info "All reviewers completed successfully"
    fi
fi

# Update PR with reviewer issue links (if any reviewers ran and PR exists)
if [[ ${#REVIEWER_WINDOWS[@]} -gt 0 && -n "$EXISTING_PR" ]]; then
    log_info "Adding reviewer issue links to PR..."

    COMMIT_SHA=$(git rev-parse HEAD)
    REVIEW_OUTPUT_DIR=".reviews/final_issue_json"

    # Build the issues section
    ISSUES_SECTION="## Code Review Issues"

    for window in "${REVIEWER_WINDOWS[@]}"; do
        # Get the URL from git note
        NOTE_REF="issues/verify_branch/$window"
        ISSUES_URL=""
        if ISSUES_URL=$(git notes --ref="$NOTE_REF" show "$COMMIT_SHA" 2>/dev/null); then
            # Get web URL from raw URL (convert raw.githubusercontent.com to github.com/blob)
            ISSUES_WEB_URL=$(echo "$ISSUES_URL" | sed 's|raw.githubusercontent.com|github.com|' | sed 's|/commit-metadata/|/blob/commit-metadata/|')

            # Count issues from local file
            LOCAL_FILE="$REVIEW_OUTPUT_DIR/$window.json"
            if [[ -f "$LOCAL_FILE" ]]; then
                CONTENT=$(cat "$LOCAL_FILE")
                if [[ "$CONTENT" == "[]" || -z "$CONTENT" || ! -s "$LOCAL_FILE" ]]; then
                    ISSUES_SECTION+="
- [$window: no issues found]($ISSUES_WEB_URL)"
                else
                    # Count items in JSON array using jq
                    ISSUE_COUNT=$(jq 'length' "$LOCAL_FILE" 2>/dev/null || echo "?")
                    ISSUES_SECTION+="
- [$window: $ISSUE_COUNT issue(s) found]($ISSUES_WEB_URL)"
                fi
            else
                # File doesn't exist, check if it was empty (stored as [])
                ISSUES_SECTION+="
- [$window: no issues found]($ISSUES_WEB_URL)"
            fi
        else
            log_warn "Could not read git note for $window"
        fi
    done

    # Update PR description with issues section
    if ! CURRENT_BODY=$(gh pr view "$EXISTING_PR" --json body --jq '.body'); then
        log_error "Failed to get current PR body for issues update"
        exit 1
    else
        # Remove existing issues section if present and append new one
        if echo "$CURRENT_BODY" | grep -q "## Code Review Issues"; then
            NEW_BODY=$(echo "$CURRENT_BODY" | awk '
                /^## Code Review Issues/ { in_issues=1; next }
                /^## / && in_issues { in_issues=0 }
                !in_issues { print }
            ')
            NEW_BODY="$NEW_BODY
$ISSUES_SECTION"
        else
            NEW_BODY="$CURRENT_BODY

$ISSUES_SECTION"
        fi

        if gh pr edit "$EXISTING_PR" --body "$NEW_BODY"; then
            log_info "PR description updated with reviewer issue links"
        else
            log_error "Failed to update PR description with reviewer issue links"
            exit 1
        fi
    fi
fi

# Call local notification script if it exists
notify_user || echo "No notify_user function defined, skipping."

exit 0
