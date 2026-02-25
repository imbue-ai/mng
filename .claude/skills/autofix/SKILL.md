---
name: autofix
description: >
  Automatically find and fix code issues in the current branch. Iteratively
  verifies, plans fixes, and implements them with separate commits. Defers
  all review to the caller.
---

# Autofix

Iteratively verify the current branch for code issues, plan and implement fixes
(each in a separate commit), and repeat until clean. This skill only performs
setup and fixing -- the caller handles review of the resulting commits.

## Instructions

### Phase 1: Setup

- Remove stale state from previous runs:
  - `rm -f .autofix/result`
  - `rm -f .reviews/final_issue_json/$(tmux display-message -t "$TMUX_PANE" -p '#W' 2>/dev/null || echo reviewer_0).json.done`
- Initial HEAD (`initial_head`): !`git rev-parse HEAD`

Determine the base branch: check the GIT_BASE_BRANCH environment variable.
If it is set, use its value. Otherwise default to main.

Create the .autofix/plans directory if it does not already exist.

### Phase 2: Fix Loop

Repeat up to 10 times:

1. Record the current HEAD as `pre_iteration_head`.
2. Read the supporting file [verify-and-fix.md](verify-and-fix.md) from this
   skill's directory. Spawn a single Task subagent
   (`subagent_type: "general-purpose"`) with its contents as the prompt.
   Prepend the line `Base branch for this project: {base_branch}` to the prompt.
3. After the subagent finishes, check if HEAD moved: compare
   `git rev-parse HEAD` to `pre_iteration_head`.
4. If HEAD did not move, no fixes were made. The branch is clean (or remaining
   issues are unfixable). Stop looping.
5. If HEAD moved, continue to the next iteration.

Important:
- Do NOT explore code, plan, or fix anything yourself. The subagent does all
  the work.
- Each iteration gets a fresh-context subagent, which is the whole point.
- Do NOT pass the subagent any information about previous iterations or previous
  fixes. It operates from a clean slate every time.

### Phase 3: Signal Completion

After the loop ends:

1. Determine the result:
   - If `git rev-parse HEAD` equals `initial_head`, check what the last
     subagent reported (it may have found issues it was unable to fix or
     unable to commit). If it encountered problems, the result is
     `error: <description of what the subagent reported>`. Otherwise the
     result is `clean`.
   - If HEAD moved past `initial_head`, the result is `fixed`.
   - If an error occurred during the fix loop, the result is `error: <description>`.

2. Write the result string to `.autofix/result`.

3. Touch the done marker file so the caller knows this skill has finished:

```bash
mkdir -p .reviews/final_issue_json
touch .reviews/final_issue_json/$(tmux display-message -t "$TMUX_PANE" -p '#W' 2>/dev/null || echo reviewer_0).json.done
```
