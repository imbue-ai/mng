#!/bin/bash
#
# main_claude_stop_hook.sh
#
# Orchestrator for stop hook scripts. Performs shared setup (precondition
# checks, fetch/merge/push, informational detection, stuck-agent tracking),
# then launches stop_hook_pr_and_ci.sh and stop_hook_reviewer.sh in parallel.

set -euo pipefail

# Read hook input JSON from stdin (must be done before anything else consumes stdin)
HOOK_INPUT=$(cat 2>/dev/null || echo '{}')

# Remove the active session marker file on exit (regardless of success/failure)
cleanup_active_file() {
    rm -f .claude/active
}
trap cleanup_active_file EXIT

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
mkdir -p .claude
echo $MAIN_CLAUDE_SESSION_ID > .claude/sessionid

# Verify that all changes are committed (fail if not)
untracked=$(git ls-files --others --exclude-standard)
staged=$(git diff --cached --name-only)
unstaged=$(git diff --name-only)

if [ -n "$untracked" ] || [ -n "$staged" ] || [ -n "$unstaged" ]; then
    echo "ERROR: Uncommitted changes detected. All changes must be committed before this hook can run." >&2
    echo "ERROR: Please commit or gitignore all files before stopping." >&2
    exit 1
fi

# Get the current tmux session name
TMUX_SESSION=$(tmux display-message -p '#S' 2>/dev/null)
if [ -z "$TMUX_SESSION" ]; then
    exit 0
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Source shared function definitions (log_error, log_warn, log_info, retry_command)
source "$SCRIPT_DIR/stop_hook_common.sh"

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
        log_info "No files changed compared to $BASE_BRANCH - this was an informational session"
        IS_INFORMATIONAL_ONLY=true
    else
        # If all changed files are .md files, consider this an informational session
        NON_MD_FILES=$(echo "$CHANGED_FILES" | grep -v '\.md$' || true)
        if [[ -z "$NON_MD_FILES" ]]; then
            log_info "Only .md files changed compared to $BASE_BRANCH - this was an informational session"
            IS_INFORMATIONAL_ONLY=true
        fi
    fi
fi

if [[ "$IS_INFORMATIONAL_ONLY" == "true" ]]; then
    log_info "No code changes detected compared to $BASE_BRANCH - this is an informational session. Exiting cleanly."
    exit 0
fi

# Track the commit hash to detect stuck agents.
# Only track if this is the main agent and it's already trying to stop (stop_hook_active=true).
# Subagents (launched by claude itself) also trigger the stop hook, and we must not
# append to reviewed_commits for those, otherwise it looks like the main agent stopped
# again and can falsely trigger the "stuck agent" detection.
STOP_HOOK_ACTIVE=$(echo "$HOOK_INPUT" | jq -r '.stop_hook_active // false')
if [[ "$STOP_HOOK_ACTIVE" == "true" ]]; then
    ( git rev-parse HEAD || echo "conflict" ) >> .claude/reviewed_commits
fi

# Check if we've reviewed the same commit 3 times in a row (agent is stuck)
if [[ -f .claude/reviewed_commits ]]; then
    LAST_THREE=$(tail -n 3 .claude/reviewed_commits)
    ENTRY_COUNT=$(echo "$LAST_THREE" | wc -l)

    if [[ $ENTRY_COUNT -ge 3 ]]; then
        UNIQUE_COUNT=$(echo "$LAST_THREE" | sort -u | wc -l)
        if [[ $UNIQUE_COUNT -eq 1 ]]; then
            echo "ERROR: This hook has been run 3 times at the same commit." >&2
            echo "ERROR: The agent appears to be stuck and unable to make progress." >&2
            echo "ERROR: Please investigate and resolve the issue manually." >&2
            exit 1
        fi
    fi
fi

# Export variables needed by child scripts
export TMUX_SESSION SCRIPT_DIR CURRENT_BRANCH BASE_BRANCH
export RED GREEN YELLOW NC

# Launch both scripts in parallel
"$SCRIPT_DIR/stop_hook_pr_and_ci.sh" &
PR_CI_PID=$!

"$SCRIPT_DIR/stop_hook_reviewer.sh" &
REVIEWER_PID=$!

# Wait for both and collect exit codes
FAILED=false

wait "$PR_CI_PID" && PR_CI_EXIT=0 || PR_CI_EXIT=$?
if [[ $PR_CI_EXIT -ne 0 ]]; then
    log_error "PR/CI hook failed (exit code $PR_CI_EXIT)"
    FAILED=true
fi

wait "$REVIEWER_PID" && REVIEWER_EXIT=0 || REVIEWER_EXIT=$?
if [[ $REVIEWER_EXIT -ne 0 ]]; then
    log_error "Reviewer hook failed (exit code $REVIEWER_EXIT)"
    FAILED=true
fi

if [[ "$FAILED" == true ]]; then
    # Propagate the first non-zero exit code
    if [[ $PR_CI_EXIT -ne 0 ]]; then
        exit $PR_CI_EXIT
    fi
    exit $REVIEWER_EXIT
fi

# Call local notification script if it exists
notify_user || echo "No notify_user function defined, skipping."

exit 0
