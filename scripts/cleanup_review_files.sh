#!/bin/bash
# Clean up old review files and create directories for a new review.
# Gets the tmux window name to scope cleanup to the current reviewer.
#
# This wrapper exists so that the !` ` expansion in command files
# does not need $() substitution, which is blocked by Claude Code's
# permission system when --dangerously-skip-permissions is not set.

set -euo pipefail

WINDOW="$(tmux display-message -t "${TMUX_PANE:-}" -p '#W' 2>/dev/null || echo reviewer_0)"

rm -rf ".reviews/initial_issue_list/$WINDOW.md"
rm -rf ".reviews/final_issue_json/$WINDOW.json"
rm -rf ".reviews/final_issue_json/$WINDOW.json.done"
mkdir -p .reviews/initial_issue_list .reviews/final_issue_json
