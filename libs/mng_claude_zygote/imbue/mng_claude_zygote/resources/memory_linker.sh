#!/bin/bash
# Memory linker for changeling agents.
#
# Watches for the Claude project directory to be created and then symlinks
# the memory directory so all Claude agents share the same project memory
# that is version-controlled in the agent's git repo.
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

echo "Memory linker: waiting for Claude project directory..."
echo "  Work dir: $WORK_DIR"
echo "  Changelings memory: $CHANGELINGS_MEMORY"
echo "  Claude projects dir: $CLAUDE_PROJECTS_DIR"

elapsed=0
while [ "$elapsed" -lt "$MAX_WAIT" ]; do
    # Look for a project directory that corresponds to our work directory.
    # Claude creates project dirs named by hashing the project path.
    if [ -d "$CLAUDE_PROJECTS_DIR" ]; then
        for project_dir in "$CLAUDE_PROJECTS_DIR"/*/; do
            if [ ! -d "$project_dir" ]; then
                continue
            fi

            MEMORY_DIR="${project_dir}memory"

            # Create the changelings memory directory if it doesn't exist
            mkdir -p "$CHANGELINGS_MEMORY"

            if [ -L "$MEMORY_DIR" ]; then
                # Already a symlink -- check if it points to the right place
                current_target=$(readlink "$MEMORY_DIR")
                if [ "$current_target" = "$CHANGELINGS_MEMORY" ]; then
                    echo "Memory already linked: $MEMORY_DIR -> $CHANGELINGS_MEMORY"
                    exit 0
                fi
            fi

            if [ -d "$MEMORY_DIR" ] && [ ! -L "$MEMORY_DIR" ]; then
                # Real directory: merge its contents into changelings memory, then replace
                rsync -a "$MEMORY_DIR/" "$CHANGELINGS_MEMORY/" 2>/dev/null || cp -a "$MEMORY_DIR/"* "$CHANGELINGS_MEMORY/" 2>/dev/null || true
                rm -rf "$MEMORY_DIR"
            fi

            ln -s "$CHANGELINGS_MEMORY" "$MEMORY_DIR"
            echo "Memory linked: $MEMORY_DIR -> $CHANGELINGS_MEMORY"
            exit 0
        done
    fi

    sleep "$POLL_INTERVAL"
    elapsed=$((elapsed + POLL_INTERVAL))
done

echo "Warning: timed out waiting for Claude project directory (waited ${MAX_WAIT}s)" >&2
exit 1
