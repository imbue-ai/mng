#!/bin/bash
#
# stop_hook_common.sh
#
# Shared logic for stop hook scripts. This file is meant to be sourced
# (not executed directly) by stop_hook_pr_and_ci.sh and stop_hook_reviewer.sh.
#
# When sourced, this script:
#   1. Reads hook input JSON from stdin
#   2. Sets up cleanup of .claude/active on exit
#   3. Exits cleanly if not in tmux or not the main claude session
#   4. Verifies that all changes are committed (fails if not)
#   5. Gets the tmux session name
#   6. Defines colors, log functions, and retry_command
#   7. Sets CURRENT_BRANCH and BASE_BRANCH
#   8. Fetches remotes, merges base branch, pushes merge commits
#   9. Exits cleanly if this is an informational-only session (no code changes)
#
# After sourcing, the following variables are available:
#   HOOK_INPUT, TMUX_SESSION, SCRIPT_DIR, CURRENT_BRANCH, BASE_BRANCH
#
# After sourcing, the following functions are available:
#   log_error, log_warn, log_info, retry_command

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

# Get the directory of this script (needed for launching other scripts)
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
