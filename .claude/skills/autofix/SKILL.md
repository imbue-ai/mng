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

!`rm -f .autofix/result`
!`rm -f .reviews/final_issue_json/$(tmux display-message -t "$TMUX_PANE" -p '#W' || echo reviewer_0).json.done`

- Initial HEAD (`initial_head`): !`git rev-parse HEAD`

- Base branch (`base_branch`): !`echo ${GIT_BASE_BRANCH:-main}`

!`mkdir -p .autofix/plans`

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
- Each iteration MUST get a fresh-context subagent with no information from
  previous iterations.

### Phase 3: Signal Completion

After the loop ends:

1. Determine the result and write it as JSON to `.autofix/result`:

   - If `git rev-parse HEAD` equals `initial_head`, check what the last
     subagent reported (it may have found issues it was unable to fix or
     unable to commit). If it encountered problems, the status is `failed`.
     Otherwise the status is `clean`.
   - If HEAD moved past `initial_head`, the status is `fixed`.
   - If an error occurred during the fix loop, the status is `failed`.

   The JSON format is:

   ```json
   {
     "status": "<clean|fixed|failed>",
     "note": "<see below>"
   }
   ```

   The `note` field:
   - If `clean`: what the reviewer's final conclusion was (e.g. "no issues found").
   - If `failed`: what the error or problem was.
   - If `fixed`: by default empty string, but include any important context
     if needed.

3. Touch the done marker file so the caller knows this skill has finished:

```bash
mkdir -p .reviews/final_issue_json
touch .reviews/final_issue_json/$(tmux display-message -t "$TMUX_PANE" -p '#W' 2>/dev/null || echo reviewer_0).json.done
```
