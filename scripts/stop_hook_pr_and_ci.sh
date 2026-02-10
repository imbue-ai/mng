#!/bin/bash
#
# stop_hook_pr_and_ci.sh
#
# Ensures a PR is created/updated and that all CI tests pass.
#
# Normally launched in parallel by main_claude_stop_hook.sh (which handles
# common setup once). Can also be run standalone -- in that case,
# stop_hook_common.sh performs the full setup automatically.

set -euo pipefail

# Source shared logic. When launched from main_claude_stop_hook.sh this is a
# fast no-op (variables already exported, just redefines functions). When run
# standalone it performs the full setup (stdin, preconditions, fetch/merge/push).
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/stop_hook_common.sh"

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

EXISTING_PR=""

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

exit 0
