---
name: create-github-issues
description: Convert a file containing identified issues into GitHub issues. Use after running identify-* commands to create corresponding GitHub issues.
---

# Creating GitHub Issues from Issue Files

This skill provides guidelines for converting issue files (created by the identify-* commands) into GitHub issues.

## Overview

Issue files are markdown files located in `_tasks/<category>/` directories within a library. Each file contains a list of identified issues (inconsistencies, style issues, outdated docstrings, etc.) that should be tracked as GitHub issues.

## Process

Follow these steps to convert an issue file into GitHub issues:

### 1. Find the Newly Created Issue File

Look for recently created markdown files in the library's `_tasks/` directory. The file will be in a subdirectory that indicates the issue category:

- `_tasks/inconsistencies/` - Code inconsistencies
- `_tasks/docs/` - Documentation and code disagreements
- `_tasks/style/` - Style guide violations
- `_tasks/docstrings/` - Outdated docstrings

### 2. Determine the Label

The label for GitHub issues should be based on the folder name under `_tasks/` where the issue file was created. For example:

- If the file is in `_tasks/docstrings/`, the label should be `docstrings`
- If the file is in `_tasks/inconsistencies/`, the label should be `inconsistencies`
- If the file is in `_tasks/style/`, the label should be `style`
- If the file is in `_tasks/docs/`, the label should be `docs`

### 3. Load All Existing GitHub Issues with This Label

Query GitHub for all existing issues with this label using:

```bash
gh issue list --label "<label>" --state all --json number,title,body,state --limit 1000
```

This returns all issues (both open and closed) with the specified label so you can avoid creating duplicates.

### 4. Create New GitHub Issues

For each issue in the file that does not already exist in GitHub:

1. Parse the issue from the markdown file (each issue is typically a numbered section like `## 1. <title>`)
2. Check if a similar issue already exists by comparing titles
3. If no matching issue exists, create a new one:

```bash
gh issue create --title "<Short description>" --body "<Full issue content>" --label "<label>"
```

The body should include:
- The description of the issue
- File names and line numbers where applicable
- The recommendation for how to fix it

### 5. Update Existing Issues

For any issues that already exist in GitHub but have new data or details in the file:

```bash
gh issue edit <issue_number> --body "<Updated body content>"
```

Only update if there is meaningful new information to add.

### 6. Refresh the Issue List

After creating and updating issues, query GitHub again to get a consolidated view:

```bash
gh issue list --label "<label>" --state open --json number,title,body,createdAt --limit 1000
```

### 7. Rank Issues by Importance

Review all open issues with this label and create your own ranking from most important to least important. Consider:

- Impact on code quality and maintainability
- How confusing or misleading the current state is
- Effort required to fix
- Whether it blocks other work

### 8. Prune Excess Issues

If there are more than 50 open issues with this label, close the least important ones until only 50 remain:

```bash
gh issue close <issue_number> --comment "Closing as lower priority - too many issues with this label."
```

### 9. Update Timestamps for Sorting

In reverse order (from least important to most important), update each open issue by adding or updating a "last updated" timestamp at the end of the description. This will cause them to sort properly when viewing by recently updated.

For each issue, from least important to most important:

```bash
gh issue edit <issue_number> --body "<existing body>

---
Last updated: <current timestamp>"
```

Get the current timestamp using:
```bash
date -u +"%Y-%m-%dT%H:%M:%SZ"
```

By updating from least to most important, the most important issues will have the most recent "updated at" timestamp and will appear first when sorting by recently updated.

## Notes

- The issue file formats vary slightly between different identify-* commands, but all follow a similar pattern with numbered sections
- Always check for duplicates before creating new issues
- Use your judgment when determining if an existing issue should be updated vs. left as-is
- The 50-issue limit per label helps keep the issue backlog manageable
