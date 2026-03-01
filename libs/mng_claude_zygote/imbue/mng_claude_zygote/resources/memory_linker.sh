#!/bin/bash
# Memory linker for changeling agents.
#
# Watches for the Claude project directory to be created and then symlinks
# the memory directory so all Claude agents share the same project memory
# that is version-controlled in the agent's git repo.
#
# Claude names project directories by replacing / with - in the absolute path,
# e.g. /home/user/my-project -> -home-user-my-project
#
# Creates:
#   ~/.claude/projects/<hash>/memory/ -> <work_dir>/.changelings/memory/
#
# Usage: memory_linker.sh <work_dir>
#
# Runs in the background: polls until the project directory exists, creates
# the symlink, then exits.

set -euo pipefail

WORK_DIR="${1:?Usage: memory_linker.sh <work_dir>}"
CHANGELINGS_MEMORY="$WORK_DIR/.changelings/memory"
CLAUDE_PROJECTS_DIR="$HOME/.claude/projects"
POLL_INTERVAL=5
MAX_WAIT=300  # 5 minutes max

# Compute the expected project directory name from the work_dir.
# Claude uses the convention: absolute path with / replaced by -
# e.g. /home/user/project -> -home-user-project
compute_expected_project_name() {
    local abs_path
    abs_path=$(cd "$WORK_DIR" && pwd)
    echo "$abs_path" | sed 's|/|-|g'
}

EXPECTED_NAME=$(compute_expected_project_name)
EXPECTED_PROJECT_DIR="$CLAUDE_PROJECTS_DIR/$EXPECTED_NAME"

echo "Memory linker: waiting for Claude project directory..."
echo "  Work dir: $WORK_DIR"
echo "  Expected project dir: $EXPECTED_PROJECT_DIR"
echo "  Changelings memory: $CHANGELINGS_MEMORY"

elapsed=0
while [ "$elapsed" -lt "$MAX_WAIT" ]; do
    if [ -d "$EXPECTED_PROJECT_DIR" ]; then
        MEMORY_DIR="$EXPECTED_PROJECT_DIR/memory"

        # Create the changelings memory directory if it doesn't exist
        mkdir -p "$CHANGELINGS_MEMORY"

        if [ -L "$MEMORY_DIR" ]; then
            # Already a symlink -- check if it points to the right place
            current_target=$(readlink "$MEMORY_DIR")
            if [ "$current_target" = "$CHANGELINGS_MEMORY" ]; then
                echo "Memory already linked: $MEMORY_DIR -> $CHANGELINGS_MEMORY"
                exit 0
            fi
            # Symlink points elsewhere -- remove it and re-create
            echo "Updating memory symlink (was: $current_target)"
            rm "$MEMORY_DIR"
        elif [ -d "$MEMORY_DIR" ]; then
            # Real directory: merge its contents into changelings memory, then replace.
            # Fail if the merge fails -- do NOT delete the original without a successful copy.
            if ! rsync -a "$MEMORY_DIR/" "$CHANGELINGS_MEMORY/"; then
                if ! cp -a "$MEMORY_DIR/"* "$CHANGELINGS_MEMORY/" 2>/dev/null; then
                    echo "Error: failed to merge existing memory directory" >&2
                    echo "  Source: $MEMORY_DIR" >&2
                    echo "  Target: $CHANGELINGS_MEMORY" >&2
                    exit 1
                fi
            fi
            rm -rf "$MEMORY_DIR"
        fi

        ln -s "$CHANGELINGS_MEMORY" "$MEMORY_DIR"
        echo "Memory linked: $MEMORY_DIR -> $CHANGELINGS_MEMORY"
        exit 0
    fi

    sleep "$POLL_INTERVAL"
    elapsed=$((elapsed + POLL_INTERVAL))
done

echo "Warning: timed out waiting for Claude project directory (waited ${MAX_WAIT}s)" >&2
exit 1
