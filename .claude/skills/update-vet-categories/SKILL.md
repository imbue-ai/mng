---
name: update-vet-categories
description: Update vet issue category overrides after editing the category .md files directly. Use when you've changed code-issue-categories.md or conversation-issue-categories.md and need to sync the override script.
---

# Updating Vet Issue Categories

This skill enables editing the issue category `.md` files directly and then updating `scripts/verify_skill_overrides.py` to match, so the generator stays consistent with your edits.

## Background

The issue category files in `.claude/agents/categories/` are generated from vet (an external repo) plus mng-specific overrides defined in `scripts/verify_skill_overrides.py`. The generator script `scripts/generate_verify_skills.py` reads vet's base categories, applies the overrides, and writes the final `.md` files.

The workflow is: the user edits the `.md` files to say what they want, then you (the agent) update the override script so the generator reproduces those edits.

## Safety Checks

Before doing any work:

1. **Ensure the working tree is clean (aside from the category file edits).** Run `git status` and confirm there are no other uncommitted changes. The override script must always be updated from a known-good committed state so that changes can be reviewed and reverted cleanly.
2. **Ensure VET_REPO is set.** The generator requires a vet checkout. Run `echo $VET_REPO` to confirm. If not set, clone it:
   ```bash
   git clone https://github.com/imbue-ai/vet /tmp/vet
   export VET_REPO=/tmp/vet
   ```

## Instructions

### 1. Update the override script

Read `scripts/verify_skill_overrides.py` to understand the existing overrides and the available override actions (`OverrideAction` enum). Then edit it to make the generator output match the `.md` file content the user wants. Keep overrides organized by the order categories appear in the output file.

### 2. Verify your work

Confirm the generator reproduces the desired files exactly:

```bash
uv run python scripts/generate_verify_skills.py --check
```

If the check fails, iterate on the overrides.

### 3. Commit

Commit the override script changes. The category files themselves should be unchanged (the whole point is making the generator reproduce them).
