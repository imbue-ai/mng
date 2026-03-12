#!/usr/bin/env bash
# Pre-commit hook: regenerate verify skill markdown from vet and check for drift.
# Skips silently if vet repo is not available.
set -euo pipefail

VET_REPO="${VET_REPO:-$HOME/vet}"
if [ ! -d "$VET_REPO/vet" ]; then
    echo "Skipping: vet repo not found at $VET_REPO (set VET_REPO to override)" >&2
    exit 0
fi

uv run python scripts/generate_verify_skills.py --vet-repo "$VET_REPO"
git diff --quiet .claude/skills/verify-conversation/categories.md .claude/skills/autofix/verify-and-fix.md
