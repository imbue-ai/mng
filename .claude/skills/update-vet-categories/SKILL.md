---
name: update-vet-categories
description: Update the vet issue category override script to match changes in the generated category files. Use when vet upstream has changed and the category .md files need updating.
---

# Updating Vet Issue Categories

This skill guides the process of updating `scripts/verify_skill_overrides.py` to reflect changes in vet's upstream issue categories. The override script is the source of truth for mng-specific customizations to vet's issue identification guides.

## Background

The issue category files in `.claude/agents/categories/` are generated from vet (an external repo) plus mng-specific overrides defined in `scripts/verify_skill_overrides.py`. The generator script `scripts/generate_verify_skills.py` reads vet's base categories, applies the overrides, and writes the final `.md` files.

Override actions:
- `APPEND_GUIDE` / `APPEND_EXAMPLES` / `APPEND_EXCEPTIONS` -- add content after vet's base
- `REPLACE_GUIDE` / `REPLACE_EXAMPLES` / `REPLACE_EXCEPTIONS` -- completely replace vet's base content (use when you need the output to be stable regardless of vet version)
- `ADD_CATEGORY` -- add an entirely new category (via `NEW_CATEGORIES` dict)

## Safety Checks

Before doing any work:

1. **Ensure the working tree is clean.** Run `git status` and confirm there are no uncommitted changes. The override script must always be updated from a known-good committed state so that changes can be reviewed and reverted cleanly.
2. **Ensure VET_REPO is set.** The generator requires a vet checkout. Run `echo $VET_REPO` to confirm. If not set, ask the user for the path.

## Instructions

### 1. Regenerate from current vet to see what changed

Run the generator to produce the latest output from vet + current overrides:

```bash
uv run python scripts/generate_verify_skills.py
```

Then diff the result against what's committed:

```bash
git diff .claude/agents/categories/
```

This shows you the vet upstream changes that are not yet captured by the overrides.

### 2. Analyze each change

For each changed category section, determine:

- **What changed in the guide text?** If vet simplified or rewrote the guide, you may need a `REPLACE_GUIDE` override.
- **What changed in examples?** If examples were added, removed, or reworded, you may need `REPLACE_EXAMPLES`.
- **What changed in exceptions?** Same logic -- use `REPLACE_EXCEPTIONS` if needed.

Key decision: use APPEND when you are adding mng-specific content on top of vet's base. Use REPLACE when you want the override to be the sole source of truth for that section (i.e., vet's base content for that field is completely overridden).

### 3. Update the override script

Edit `scripts/verify_skill_overrides.py`:

- For each changed category, add or update the appropriate `Override` entries in `CATEGORY_EXTENSIONS`.
- When using `REPLACE_*`, provide the complete desired content (including any items that originally came from vet's base, since REPLACE discards the base entirely).
- When converting from `APPEND_*` to `REPLACE_*`, remove the old APPEND entry and add a REPLACE entry with the full desired content.
- Keep overrides organized by the order categories appear in the output file.

### 4. Regenerate and verify

```bash
uv run python scripts/generate_verify_skills.py
uv run python scripts/generate_verify_skills.py --check
```

Both commands should succeed. The `--check` command verifies the on-disk files match what the generator produces.

### 5. Review the final diff

```bash
git diff scripts/verify_skill_overrides.py
git diff .claude/agents/categories/
```

Verify that:
- The override script changes are minimal and correct
- The category file changes match the desired vet upstream changes
- No unintended categories were affected

### 6. Commit

Commit both the override script changes and the regenerated category files together in a single commit.
