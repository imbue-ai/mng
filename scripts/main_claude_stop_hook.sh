#!/bin/bash
# Stop hook script that messages reviewer tmux windows
# Only runs if the git repo is clean (all changes committed)

set -euo pipefail

# Read hook input JSON from stdin (must be done before anything else consumes stdin)
HOOK_INPUT=$(cat 2>/dev/null || echo '{}')

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

# ensure the folder exists
mkdir -p .claude

# Only track the commit hash if this is the main agent and it's already trying to stop (stop_hook_active=true).
# Subagents (launched by claude itself) also trigger the stop hook, and we must not
# append to reviewed_commits for those, otherwise it looks like the main agent stopped
# again and can falsely trigger the "stuck agent" detection.
STOP_HOOK_ACTIVE=$(echo "$HOOK_INPUT" | jq -r '.stop_hook_active // false')
if [[ "$STOP_HOOK_ACTIVE" == "true" ]]; then
    ( git rev-parse HEAD || echo "conflict" ) >> .claude/reviewed_commits
fi

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

# Ensure a PR exists for this branch
CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD)
BASE_BRANCH="${GIT_BASE_BRANCH:-main}"

# Fetch all remotes and merge base branch to stay up-to-date
log_info "Fetching all remotes..."
git fetch --all

# Only push the base branch if it doesn't already exist on the origin
if ! git rev-parse --verify "origin/$BASE_BRANCH" >/dev/null 2>&1; then
    log_info "Pushing base branch to origin (not yet present remotely)..."
    if ! retry_command 3 git push origin "$BASE_BRANCH"; then
        log_error "Failed to push base branch after retries"
        exit 1
    fi
fi

# Merge the base branch from origin (if it exists)
if git rev-parse --verify "origin/$BASE_BRANCH" >/dev/null 2>&1; then
    log_info "Merging origin/$BASE_BRANCH..."
    if ! git merge "origin/$BASE_BRANCH" --no-edit; then
        log_error "Merge conflict detected while merging origin/$BASE_BRANCH."
        log_error "Please resolve the merge conflicts before continuing."
        exit 2
    fi
fi

# Merge the local base branch (if it exists)
if git rev-parse --verify "$BASE_BRANCH" >/dev/null 2>&1; then
    log_info "Merging $BASE_BRANCH..."
    if ! git merge "$BASE_BRANCH" --no-edit; then
        log_error "Merge conflict detected while merging $BASE_BRANCH."
        log_error "Please resolve the merge conflicts before continuing."
        exit 2
    fi
fi

# Push merge commits (if any were created)
log_info "Pushing any merge commits..."
if ! retry_command 3 git push origin HEAD; then
    log_error "Failed to push merge commits after retries"
    exit 1
fi

# Check if there are any non-markdown file changes compared to the base branch
IS_INFORMATIONAL_ONLY=false
if [[ "$CURRENT_BRANCH" == "$BASE_BRANCH" ]]; then
    log_info "Currently on base branch ($BASE_BRANCH) - no PR needed"
    IS_INFORMATIONAL_ONLY=true
else
    # Get files that have changed since the (now updated) base branch
    CHANGED_FILES=$(git diff --name-only "$BASE_BRANCH"...HEAD 2>/dev/null || echo "")
    if [[ -z "$CHANGED_FILES" ]]; then
        log_info "No files changed compared to $BASE_BRANCH - this was an informational session, skipping PR creation"
        IS_INFORMATIONAL_ONLY=true
    else
        # If all changed files are .md files, consider this an informational session
        NON_MD_FILES=$(echo "$CHANGED_FILES" | grep -v '\.md$' || true)
        if [[ -z "$NON_MD_FILES" ]]; then
            log_info "Only .md files changed compared to $BASE_BRANCH - this was an informational session, skipping PR creation"
            IS_INFORMATIONAL_ONLY=true
        fi
    fi
fi

if [[ "$IS_INFORMATIONAL_ONLY" == "true" ]]; then
    log_info "No code changes detected compared to $BASE_BRANCH - this is an informational session. Exiting cleanly."
    exit 0
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
    local pr_body="Automated PR created by Claude Code session."

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
    if NEW_PR=$(create_new_pr "$CURRENT_BRANCH"); then
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
    if NEW_PR=$(create_new_pr "$NEW_TITLE"); then
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
fi

# Initialize PR status as pending before polling
echo "pending" > .claude/pr_status

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

# Wait for all reviewer background jobs to complete
if [[ ${#REVIEWER_PIDS[@]} -gt 0 ]]; then
    log_info "Waiting for ${#REVIEWER_PIDS[@]} reviewer(s) to complete..."
    REVIEWER_FAILED=false

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
                log_error "Reviewer process $pid failed with internal error (exit code $EXIT_CODE)"
                log_error "This indicates a problem with the review infrastructure, not code issues."
                log_error "Exit code 3 = timeout waiting for review"
                exit $EXIT_CODE
            fi
        fi
    done
    if [[ "$REVIEWER_FAILED" == true ]]; then
        log_error "Some issues were identified by the review agent!"
        log_error "Run 'cat .reviews/final_issue_json/*.json' to see the issues."
        log_error "You MUST fix any CRITICAL or MAJOR issues (with confidence >= 0.7) before trying again."
        exit 2
    else
        log_info "All reviewers completed successfully"
    fi
fi

# Call local notification script if it exists
notify_user || echo "No notify_user function defined, skipping."

exit 0
